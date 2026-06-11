from app.config import Settings
from app.llm_client import SYSTEM_PROMPT
from app.query_rewriter import QueryRewriter
from app.rag_pipeline import LOW_CONFIDENCE_ANSWER, NOT_FOUND_ANSWER, RAGPipeline
from app.schemas import ChatResponse, RetrievedChunk


class FakeVectorStore:
    def add_chunks(self, chunks):  # type: ignore[no-untyped-def]
        return len(chunks)

    def query(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        return []

    def reset(self) -> None:
        pass

    def count(self) -> int:
        return 0

    def is_available(self) -> bool:
        return True


class EmptyRetriever:
    def retrieve_context(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        return []


class SourceRetriever:
    def retrieve_context(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                text="La demande d'accès doit inclure le rôle et une justification opérationnelle.",
                metadata={"file_name": "procedure_acces.pdf", "page": 2, "chunk_id": "chunk-4"},
                score=0.91,
            )
        ]


class MultiSourceRetriever:
    def retrieve_context(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                text="Le support traite les incidents et les demandes d'assistance.",
                metadata={"file_name": "faq_support.txt", "chunk_id": "sample-support-1"},
                score=0.97,
            ),
            RetrievedChunk(
                text="Toute demande d'accès doit préciser le rôle attendu et la justification opérationnelle.",
                metadata={"file_name": "procedure_acces.txt", "chunk_id": "sample-acces-1"},
                score=0.86,
            ),
            RetrievedChunk(
                text="Le support vérifie l'identité avant une réinitialisation du mot de passe.",
                metadata={"file_name": "procedure_mot_de_passe.txt", "chunk_id": "sample-password-1"},
                score=0.82,
            ),
            RetrievedChunk(
                text="Les bonnes pratiques d'utilisation interdisent le partage d'identifiants.",
                metadata={"file_name": "politique_utilisation.txt", "chunk_id": "sample-policy-1"},
                score=0.79,
            ),
            RetrievedChunk(
                text="Le rapport mensuel inclut le périmètre et les indicateurs suivis.",
                metadata={"file_name": "procedure_creation_rapport.txt", "chunk_id": "sample-report-1"},
                score=0.76,
            ),
        ]


class SummaryWithUnrelatedDocumentRetriever:
    def retrieve_context(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                text="Expériences professionnelles du candidat.",
                metadata={"file_name": "lettre_presentation.pdf", "chunk_id": "letter-1"},
                score=0.99,
            ),
            RetrievedChunk(
                text="Procédure de demande d'accès.",
                metadata={"file_name": "procedure_acces.txt", "chunk_id": "access-1"},
                score=0.40,
            ),
            RetrievedChunk(
                text="Procédure de réinitialisation.",
                metadata={"file_name": "procedure_mot_de_passe.txt", "chunk_id": "password-1"},
                score=0.38,
            ),
        ]


class FakeLLM:
    def generate_answer(self, question: str, context: str) -> str:
        assert "procedure_acces.pdf" in context
        return "La demande d'accès doit inclure le rôle et une justification opérationnelle."

    def is_available(self) -> bool:
        return True


class RefusalLLM:
    def generate_answer(self, question: str, context: str) -> str:
        return "Je ne trouve pas cette information dans les documents fournis."

    def is_available(self) -> bool:
        return True


class CaptureLLM:
    def __init__(self) -> None:
        self.context = ""

    def generate_answer(self, question: str, context: str) -> str:
        self.context = context
        return "La demande d'accès doit être justifiée."

    def is_available(self) -> bool:
        return True


class SummaryLLM:
    def generate_answer(self, question: str, context: str) -> str:
        return "Les procédures disponibles couvrent les accès et les mots de passe."

    def is_available(self) -> bool:
        return True


class LowConfidenceRetriever:
    def retrieve_context(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                text="Passage trop générique.",
                metadata={"file_name": "general.txt", "chunk_id": "generic-1"},
                score=0.20,
            )
        ]


class FakeRewriteClient:
    def rewrite(self, question: str, history: list[str]) -> str:
        return "Quelle est la procédure interne pour demander un accès SharePoint ?"


def test_pipeline_refuses_when_no_context() -> None:
    pipeline = RAGPipeline(
        config=Settings(),
        vector_store=FakeVectorStore(),
        retriever=EmptyRetriever(),
        llm_client=FakeLLM(),
    )

    response = pipeline.answer_question("Question sans réponse", top_k=5)

    assert isinstance(response, ChatResponse)
    assert response.answer == NOT_FOUND_ANSWER
    assert response.sources == []


def test_pipeline_returns_sources() -> None:
    pipeline = RAGPipeline(
        config=Settings(),
        vector_store=FakeVectorStore(),
        retriever=SourceRetriever(),
        llm_client=FakeLLM(),
    )

    response = pipeline.answer_question("Quelle information fournir ?", top_k=5)

    assert "justification opérationnelle" in response.answer
    assert len(response.sources) == 1
    assert response.sources[0].file_name == "procedure_acces.pdf"
    assert response.sources[0].page == "2"


def test_pipeline_drops_sources_when_answer_refuses() -> None:
    pipeline = RAGPipeline(
        config=Settings(),
        vector_store=FakeVectorStore(),
        retriever=SourceRetriever(),
        llm_client=RefusalLLM(),
    )

    response = pipeline.answer_question("Question hors documents", top_k=5)

    assert response.answer == NOT_FOUND_ANSWER
    assert response.sources == []


def test_pipeline_formats_context_for_ollama_prompt() -> None:
    llm = CaptureLLM()
    pipeline = RAGPipeline(
        config=Settings(),
        vector_store=FakeVectorStore(),
        retriever=SourceRetriever(),
        llm_client=llm,
    )

    response = pipeline.answer_question("Comment demander un accès ?", top_k=5)

    assert "file_name: procedure_acces.pdf" in llm.context
    assert "page: 2" in llm.context
    assert "chunk_id: chunk-4" in llm.context
    assert "score: 0.910" in llm.context
    assert "excerpt:" in llm.context
    assert len(response.sources) == 1


def test_ollama_system_prompt_requires_exact_refusal() -> None:
    assert "Tu réponds uniquement à partir des extraits fournis." in SYSTEM_PROMPT
    assert "Je ne trouve pas cette information dans les documents fournis." in SYSTEM_PROMPT
    assert "- Aucune source pertinente trouvée." in SYSTEM_PROMPT


def test_pipeline_profile_prioritizes_access_source_for_ollama_context() -> None:
    llm = CaptureLLM()
    pipeline = RAGPipeline(
        config=Settings(),
        vector_store=FakeVectorStore(),
        retriever=MultiSourceRetriever(),
        llm_client=llm,
    )

    response = pipeline.answer_question("comment demander un acces", top_k=5, routing_profile="access_request")

    assert len(response.sources) == 1
    assert response.sources[0].file_name == "procedure_acces.txt"
    assert "file_name: procedure_acces.txt" in llm.context
    assert "file_name: faq_support.txt" not in llm.context


def test_pipeline_profile_prioritizes_password_source_for_ollama_context() -> None:
    pipeline = RAGPipeline(
        config=Settings(),
        vector_store=FakeVectorStore(),
        retriever=MultiSourceRetriever(),
        llm_client=CaptureLLM(),
    )

    response = pipeline.answer_question("mot de passe oublie", top_k=5, routing_profile="password_reset")

    assert len(response.sources) == 1
    assert response.sources[0].file_name == "procedure_mot_de_passe.txt"


def test_pipeline_profile_global_summary_keeps_multiple_sources() -> None:
    pipeline = RAGPipeline(
        config=Settings(),
        vector_store=FakeVectorStore(),
        retriever=MultiSourceRetriever(),
        llm_client=CaptureLLM(),
    )

    response = pipeline.answer_question("resumer les procedures", top_k=5, routing_profile="global_summary")

    assert len(response.sources) == 5
    assert {source.file_name for source in response.sources} == {
        "procedure_acces.txt",
        "procedure_mot_de_passe.txt",
        "procedure_creation_rapport.txt",
        "faq_support.txt",
        "politique_utilisation.txt",
    }


def test_pipeline_score_margin_keeps_only_near_best_sources() -> None:
    llm = CaptureLLM()
    pipeline = RAGPipeline(
        config=Settings(),
        vector_store=FakeVectorStore(),
        retriever=MultiSourceRetriever(),
        llm_client=llm,
    )

    response = pipeline.answer_question(
        "question ciblée",
        top_k=5,
        score_margin=0.05,
    )

    assert len(response.sources) == 1
    assert response.sources[0].file_name == "faq_support.txt"


def test_pipeline_refuses_low_confidence_context_before_calling_llm() -> None:
    pipeline = RAGPipeline(
        config=Settings(rag_confidence_enabled=True, rag_min_confidence=0.35),
        vector_store=FakeVectorStore(),
        retriever=LowConfidenceRetriever(),
        llm_client=CaptureLLM(),
    )

    response = pipeline.answer_question("Question précise sans bonne source")

    assert response.answer == NOT_FOUND_ANSWER
    assert response.sources == []
    assert pipeline.last_diagnostics.refused is True


def test_pipeline_rewrites_contextual_question_before_retrieval() -> None:
    pipeline = RAGPipeline(
        config=Settings(rag_query_rewrite_enabled=True),
        vector_store=FakeVectorStore(),
        retriever=SourceRetriever(),
        llm_client=CaptureLLM(),
        query_rewriter=QueryRewriter(Settings(rag_query_rewrite_enabled=True), FakeRewriteClient()),
    )

    response = pipeline.answer_question("Et pour les accès ?", history=["Nous parlons de SharePoint."])

    assert response.sources
    assert pipeline.last_diagnostics.query_rewrite_used is True
    assert pipeline.last_diagnostics.question_rewritten.startswith("Quelle est la procédure")


def test_global_summary_keeps_low_confidence_procedures_and_deprioritizes_unrelated_letter() -> None:
    pipeline = RAGPipeline(
        config=Settings(rag_confidence_enabled=True, rag_min_confidence=0.80),
        vector_store=FakeVectorStore(),
        retriever=SummaryWithUnrelatedDocumentRetriever(),
        llm_client=SummaryLLM(),
    )

    response = pipeline.answer_question(
        "Résume les procédures disponibles.",
        routing_profile="global_summary",
    )

    assert response.sources
    assert response.sources[0].file_name == "procedure_acces.txt"
    assert pipeline.last_diagnostics.refused is False
