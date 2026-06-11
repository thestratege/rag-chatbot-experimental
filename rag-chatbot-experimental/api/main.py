from __future__ import annotations

import logging
from dataclasses import asdict
from time import perf_counter

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import auth as auth_module
from app.auth import UserContext, effective_groups, require_auth, require_role
from app.config import settings
from app.conversation_manager import ConversationManager
from app.intent_router import IntentRouter
from app.intent_router import normalize_text
from app.embeddings import EmbeddingError
from app.llm_client import LLMError
from app.provider_router import (
    ABSENT_WITH_SOURCES,
    OpenRouterRAGLLMClient,
    ProviderAnswer,
    ProviderRouter,
    normalize_absent_answer,
)
from app.rag_pipeline import RAGPipeline
from app.rag_audit import RAGAuditLogger
from app.retrieval_only_pipeline import RetrievalOnlyPipeline
from app.sharepoint_simulator import SharePointSimulator
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationResetRequest,
    ConversationResetResponse,
    FrontendChatRequest,
    FrontendChatResponse,
    HealthResponse,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG Chatbot Experimental",
    description="Prototype de chatbot documentaire RAG avec front conversationnel séparé.",
    version="0.1.0",
)

allowed_origins = list(settings.effective_allowed_origins)

@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    if not auth_module.is_public_request(request, auth_module.settings):
        try:
            auth_module.resolve_current_user(
                auth_module.settings,
                request.headers.get("Authorization"),
            )
        except HTTPException as exc:
            response = JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
            return _with_security_headers(response)

    response = await call_next(request)
    return _with_security_headers(response)


def _with_security_headers(response: Response) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if settings.allowed_frame_ancestors:
        response.headers.setdefault(
            "Content-Security-Policy",
            f"frame-ancestors {settings.allowed_frame_ancestors}",
        )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


conversation_manager = ConversationManager(settings.conversation_history_limit)
intent_router = IntentRouter()
provider_router = ProviderRouter(settings)
last_rag_diagnostics: dict[str, object] = {}


def get_pipeline() -> RAGPipeline:
    return RAGPipeline(settings)


def get_sharepoint_simulator() -> SharePointSimulator:
    if not settings.sharepoint_simulator_enabled:
        raise HTTPException(status_code=404, detail="Le simulateur SharePoint n'est pas activé.")
    return SharePointSimulator(settings)


@app.get("/")
def root(user_context: UserContext = Depends(require_auth)) -> dict[str, str]:
    logger.debug("Statut racine demandé par user=%s", user_context.user_id)
    return {"status": "ok", "service": "rag-chatbot-experimental"}


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="rag-api")


@app.post("/ingest")
def ingest(user_context: UserContext = Depends(require_role("admin"))) -> dict[str, object]:
    logger.debug("Ingestion demandée par user=%s", user_context.user_id)
    try:
        result = get_pipeline().ingest_documents()
        return {
            "status": "ok",
            "documents_loaded": result.documents_loaded,
            "chunks_created": result.chunks_created,
            "chunks_indexed": result.chunks_indexed,
            "failed_files": result.failed_files,
        }
    except Exception as exc:
        logger.exception("Erreur d'ingestion")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    user_context: UserContext = Depends(require_auth),
    demo_profile: str | None = Header(default=None, alias="X-Demo-Profile"),
) -> ChatResponse:
    logger.debug("Question RAG legacy par user=%s", user_context.user_id)
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="La question ne peut pas être vide.")

    user_groups = effective_groups(settings, user_context, demo_profile)
    started_at = perf_counter()
    try:
        pipeline = get_pipeline()
        if settings.sharepoint_simulator_enabled:
            response = pipeline.answer_question(
                request.question,
                request.top_k,
                allowed_groups=user_groups,
                score_margin=None if _is_summary_request(request.question) else 0.07,
            )
        else:
            response = pipeline.answer_question(request.question, request.top_k)
        diagnostics = _pipeline_diagnostics(pipeline)
        _audit_rag(
            request.question,
            response.answer,
            response.sources,
            "ollama",
            started_at,
            user_context,
            user_groups,
            diagnostics=diagnostics,
        )
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _audit_rag(request.question, "", [], "ollama", started_at, user_context, user_groups, str(exc))
        logger.exception("Erreur de génération RAG")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat", response_model=FrontendChatResponse)
def conversational_chat(
    request: FrontendChatRequest,
    user_context: UserContext = Depends(require_auth),
    demo_profile: str | None = Header(default=None, alias="X-Demo-Profile"),
) -> FrontendChatResponse:
    cleaned_message = request.message.strip()
    if not cleaned_message:
        raise HTTPException(status_code=400, detail="Le message ne peut pas être vide.")

    logger.debug("Message conversationnel par user=%s", user_context.user_id)
    user_groups = effective_groups(settings, user_context, demo_profile)
    conversation_id = conversation_manager.get_or_create(request.conversation_id)
    recent_history = [message.content for message in conversation_manager.history(conversation_id)]
    intent_result = intent_router.classify(cleaned_message)
    conversation_manager.append(
        conversation_id,
        role="user",
        content=cleaned_message,
        intent=intent_result.intent,
    )

    started_at = perf_counter()
    response_routing_profile = intent_result.profile
    try:
        use_rag = _should_use_rag(intent_result.intent, recent_history, cleaned_message)
        if not use_rag:
            provider_answer = provider_router.answer_without_rag(cleaned_message, intent_result.intent)
            used_rag = False
        else:
            routing_profile = intent_result.profile if intent_result.intent == "rag_question" else None
            response_routing_profile = routing_profile
            provider_answer = _answer_documentary_question(
                cleaned_message,
                routing_profile,
                user_groups,
                recent_history,
            )
            used_rag = (
                provider_answer.provider in {"mock", "retrieval_only", "ollama"}
                or bool(provider_answer.sources)
                or provider_router.openrouter_document_context_allowed()
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (LLMError, EmbeddingError) as exc:
        if use_rag:
            _audit_rag(
                cleaned_message,
                "",
                [],
                provider_router.provider,
                started_at,
                user_context,
                user_groups,
                str(exc),
            )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        if use_rag:
            _audit_rag(
                cleaned_message,
                "",
                [],
                provider_router.provider,
                started_at,
                user_context,
                user_groups,
                str(exc),
            )
        logger.exception("Erreur endpoint conversationnel")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    conversation_manager.append(
        conversation_id,
        role="assistant",
        content=provider_answer.answer,
        intent=intent_result.intent,
    )
    if used_rag:
        _audit_rag(
            cleaned_message,
            provider_answer.answer,
            provider_answer.sources,
            provider_answer.provider,
            started_at,
            user_context,
            user_groups,
            diagnostics=provider_answer.diagnostics,
        )
    return FrontendChatResponse(
        conversation_id=conversation_id,
        answer=provider_answer.answer,
        intent=intent_result.intent,
        used_rag=used_rag,
        sources=provider_answer.sources,
        provider=provider_answer.provider,
        routing_profile=response_routing_profile,
        routing_score=intent_result.confidence,
    )


@app.post("/api/conversations/reset", response_model=ConversationResetResponse)
def reset_conversation(
    request: ConversationResetRequest,
    user_context: UserContext = Depends(require_auth),
) -> ConversationResetResponse:
    logger.debug("Reset conversation par user=%s", user_context.user_id)
    conversation_manager.get_or_create(request.conversation_id)
    conversation_manager.reset(request.conversation_id)
    return ConversationResetResponse(status="reset", conversation_id=request.conversation_id)


@app.get("/admin/index/status")
def simulator_index_status(user_context: UserContext = Depends(require_role("admin"))) -> dict[str, object]:
    logger.debug("Statut simulateur demandé par user=%s", user_context.user_id)
    return {
        **get_sharepoint_simulator().status(),
        "rag_diagnostics": {
            "retrieval_mode": "hybrid" if settings.rag_hybrid_search_enabled else "vector",
            "query_rewrite_enabled": settings.rag_query_rewrite_enabled,
            "rerank_enabled": settings.rag_rerank_enabled,
            "permission_filtering_enabled": settings.rag_permission_filtering_enabled,
            "initial_top_k": settings.rag_vector_top_k,
            "final_top_k": settings.rag_final_top_k,
            "min_confidence": settings.rag_min_confidence,
            "latest": last_rag_diagnostics,
        },
    }


@app.get("/admin/index/documents")
def simulator_index_documents(user_context: UserContext = Depends(require_role("admin"))) -> list[dict[str, object]]:
    logger.debug("Documents simulateur demandés par user=%s", user_context.user_id)
    return get_sharepoint_simulator().documents()


@app.post("/admin/index/sync")
def simulator_index_sync(user_context: UserContext = Depends(require_role("admin"))) -> dict[str, object]:
    logger.debug("Synchronisation simulateur demandée par user=%s", user_context.user_id)
    summary = get_sharepoint_simulator().sync()
    return {"status": "ok", **summary.__dict__}


@app.post("/admin/index/reset-simulator")
def simulator_index_reset(user_context: UserContext = Depends(require_role("admin"))) -> dict[str, object]:
    logger.warning("Reset simulateur demandé par user=%s", user_context.user_id)
    return {"status": "reset", **get_sharepoint_simulator().reset()}


def _answer_documentary_question(
    cleaned_message: str,
    routing_profile: str | None = None,
    allowed_groups: tuple[str, ...] | None = None,
    history: list[str] | None = None,
):
    provider = provider_router.provider
    if provider == "mock":
        return provider_router.answer_with_mock_rag(cleaned_message, routing_profile)

    if provider == "retrieval_only":
        pipeline = RetrievalOnlyPipeline(settings)
        if settings.sharepoint_simulator_enabled:
            response = pipeline.answer_question(cleaned_message, settings.top_k, None, allowed_groups)
        else:
            response = pipeline.answer_question(cleaned_message, settings.top_k, routing_profile)
        return ProviderAnswer(answer=response.answer, sources=response.sources, provider="retrieval_only")

    if routing_profile == "unknown_documentary":
        return ProviderAnswer(answer=ABSENT_WITH_SOURCES, sources=[], provider=provider)

    if provider == "openrouter":
        if not provider_router.openrouter_document_context_allowed():
            answer = (
                "Le provider OpenRouter est configuré, mais l'envoi de contexte documentaire est "
                "désactivé par sécurité. Utilisez LLM_PROVIDER=mock pour la démo sans modèle ou "
                "LLM_PROVIDER=ollama pour interroger les vrais documents localement."
            )
            return ProviderAnswer(answer=answer, sources=[], provider="openrouter")
        pipeline = RAGPipeline(settings, llm_client=OpenRouterRAGLLMClient(settings))
    else:
        pipeline = get_pipeline()

    if settings.sharepoint_simulator_enabled:
        response = _pipeline_answer(
            pipeline,
            cleaned_message,
            settings.top_k,
            None,
            allowed_groups,
            score_margin=None if _is_summary_request(cleaned_message) else 0.07,
            history=history,
        )
    else:
        response = _pipeline_answer(
            pipeline,
            cleaned_message,
            settings.top_k,
            routing_profile,
            history=history,
        )
    response = normalize_absent_answer(response)
    return ProviderAnswer(
        answer=response.answer,
        sources=response.sources,
        provider=provider,
        diagnostics=_pipeline_diagnostics(pipeline),
    )


def _audit_rag(
    question: str,
    answer: str,
    sources: list,
    provider: str,
    started_at: float,
    user_context: UserContext,
    user_groups: tuple[str, ...],
    error: str | None = None,
    diagnostics: dict[str, object] | None = None,
) -> None:
    global last_rag_diagnostics
    last_rag_diagnostics = diagnostics or {}
    RAGAuditLogger(settings).write(
        question=question,
        provider=provider,
        sources=sources,
        response_time_ms=round((perf_counter() - started_at) * 1000),
        user_context=user_context,
        user_groups=user_groups,
        answer=answer,
        error=error,
        diagnostics=diagnostics,
    )


def _is_summary_request(question: str) -> bool:
    normalized = normalize_text(question)
    return any(term in normalized for term in ("resume", "synthese", "documents disponibles", "vue d ensemble"))


def _should_use_rag(intent: str, history: list[str], message: str = "") -> bool:
    if intent == "rag_question":
        return True
    local_document_provider = provider_router.provider in {"retrieval_only", "ollama"}
    if intent == "unknown" and local_document_provider:
        return True
    if intent == "clarification_needed" and local_document_provider and "?" in message:
        return True
    return settings.rag_query_rewrite_enabled and bool(history) and intent in {"clarification_needed", "unknown"}


def _pipeline_answer(
    pipeline: object,
    question: str,
    top_k: int,
    routing_profile: str | None,
    allowed_groups: tuple[str, ...] | None = None,
    *,
    score_margin: float | None = None,
    history: list[str] | None = None,
) -> ChatResponse:
    kwargs: dict[str, object] = {"history": history}
    if allowed_groups is not None:
        kwargs["allowed_groups"] = allowed_groups
    if score_margin is not None:
        kwargs["score_margin"] = score_margin
    try:
        return pipeline.answer_question(question, top_k, routing_profile, **kwargs)  # type: ignore[attr-defined]
    except TypeError as exc:
        if "history" not in str(exc):
            raise
        kwargs.pop("history", None)
        return pipeline.answer_question(question, top_k, routing_profile, **kwargs)  # type: ignore[attr-defined]


def _pipeline_diagnostics(pipeline: object) -> dict[str, object]:
    diagnostics = getattr(pipeline, "last_diagnostics", None)
    return asdict(diagnostics) if diagnostics is not None else {}
