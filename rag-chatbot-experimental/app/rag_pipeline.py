from __future__ import annotations

import logging
from dataclasses import replace

from app.chunker import TextChunker
from app.config import Settings, settings
from app.document_routing import expected_file_for_profile
from app.document_loader import DocumentLoader
from app.embeddings import OllamaEmbeddingClient
from app.intent_router import normalize_text
from app.llm_client import OllamaLLMClient
from app.query_rewriter import QueryRewriter
from app.retriever import Retriever
from app.schemas import ChatResponse, IngestionResult, RetrievalDiagnostics, RetrievalResult, RetrievedChunk, Source
from app.vector_store import VectorStore, build_vector_store


logger = logging.getLogger(__name__)

NOT_FOUND_ANSWER = "Je ne trouve pas cette information dans les documents fournis."
LOW_CONFIDENCE_ANSWER = (
    "Je ne trouve pas suffisamment d’éléments fiables dans les documents disponibles. "
    "Pouvez-vous préciser le document, le service ou la procédure concernée ?"
)


class RAGPipeline:
    def __init__(
        self,
        config: Settings = settings,
        loader: DocumentLoader | None = None,
        chunker: TextChunker | None = None,
        embedding_client: OllamaEmbeddingClient | None = None,
        vector_store: VectorStore | None = None,
        retriever: Retriever | None = None,
        llm_client: OllamaLLMClient | None = None,
        query_rewriter: QueryRewriter | None = None,
    ) -> None:
        self.config = config
        self.loader = loader or DocumentLoader(config.documents_dir)
        self.chunker = chunker or TextChunker(config.chunk_size, config.chunk_overlap)
        self.embedding_client = embedding_client or OllamaEmbeddingClient(config)
        self.vector_store = vector_store or build_vector_store(config)
        self.retriever = retriever or Retriever(config, self.embedding_client, self.vector_store)
        self.llm_client = llm_client or OllamaLLMClient(config)
        self.query_rewriter = query_rewriter or QueryRewriter(config)
        self.last_diagnostics = RetrievalDiagnostics(
            question_original="",
            question_rewritten="",
            query_rewrite_used=False,
            retrieval_mode="hybrid" if config.rag_hybrid_search_enabled else "vector",
            retrieved_chunks_initial=0,
            retrieved_chunks_final=0,
            confidence=0.0,
        )

    def ingest_documents(self) -> IngestionResult:
        documents, failed_files = self.loader.load_all()
        if not documents:
            logger.warning("Ingestion arrêtée: aucun contenu documentaire exploitable.")
            return IngestionResult(documents_loaded=0, chunks_created=0, chunks_indexed=0, failed_files=failed_files)

        chunks = self.chunker.chunk_documents(documents)
        if not chunks:
            logger.warning("Ingestion arrêtée: aucun chunk créé.")
            return IngestionResult(
                documents_loaded=len(documents),
                chunks_created=0,
                chunks_indexed=0,
                failed_files=failed_files,
            )

        embedded_chunks = self.embedding_client.embed_documents(chunks)
        indexed_count = self.vector_store.add_chunks(embedded_chunks)
        return IngestionResult(
            documents_loaded=len(documents),
            chunks_created=len(chunks),
            chunks_indexed=indexed_count,
            failed_files=failed_files,
        )

    def reset_vector_store(self) -> None:
        self.vector_store.reset()

    def answer_question(
        self,
        question: str,
        top_k: int | None = None,
        routing_profile: str | None = None,
        allowed_groups: tuple[str, ...] | None = None,
        score_margin: float | None = None,
        history: list[str] | None = None,
    ) -> ChatResponse:
        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("La question ne peut pas être vide.")

        rewrite = self.query_rewriter.rewrite(cleaned_question, history)
        retrieval_question = rewrite.rewritten_question
        diversity_enabled = routing_profile == "global_summary" or _is_multi_document_question(retrieval_question)
        retrieval_result = self._retrieve(
            retrieval_question,
            top_k,
            allowed_groups,
            diversity_enabled=diversity_enabled,
            question_original=cleaned_question,
            query_rewrite_used=rewrite.used,
        )
        retrieved_chunks = retrieval_result.chunks
        if score_margin is not None:
            retrieved_chunks = _filter_by_score_margin(retrieved_chunks, score_margin)
        retrieved_chunks = _select_chunks_for_profile(retrieved_chunks, routing_profile)
        self.last_diagnostics = replace(
            retrieval_result.diagnostics,
            retrieved_chunks_final=len(retrieved_chunks),
            confidence=round((retrieved_chunks[0].score or 0.0) if retrieved_chunks else 0.0, 4),
        )
        if not retrieved_chunks:
            self.last_diagnostics = replace(self.last_diagnostics, refused=True)
            return ChatResponse(answer=NOT_FOUND_ANSWER, sources=[])
        if self._should_refuse_for_confidence(retrieval_question, retrieved_chunks, routing_profile):
            self.last_diagnostics = replace(self.last_diagnostics, refused=True)
            answer = LOW_CONFIDENCE_ANSWER if _question_is_vague(retrieval_question) else NOT_FOUND_ANSWER
            return ChatResponse(answer=answer, sources=[])

        context = self._format_context(retrieved_chunks)
        answer = self.llm_client.generate_answer(retrieval_question, context)
        if NOT_FOUND_ANSWER.lower() in answer.lower():
            self.last_diagnostics = replace(self.last_diagnostics, refused=True)
            return ChatResponse(answer=NOT_FOUND_ANSWER, sources=[])
        answer = _ensure_sources_in_answer(answer, retrieved_chunks)
        return ChatResponse(answer=answer, sources=[_source_from_chunk(chunk) for chunk in retrieved_chunks])

    def _retrieve(
        self,
        question: str,
        top_k: int | None,
        allowed_groups: tuple[str, ...] | None,
        *,
        diversity_enabled: bool,
        question_original: str,
        query_rewrite_used: bool,
    ) -> RetrievalResult:
        if hasattr(self.retriever, "retrieve_with_diagnostics"):
            return self.retriever.retrieve_with_diagnostics(
                question,
                top_k=top_k or self.config.rag_final_top_k,
                allowed_groups=allowed_groups,
                diversity_enabled=diversity_enabled,
                question_original=question_original,
                query_rewrite_used=query_rewrite_used,
            )
        effective_groups = allowed_groups if self.config.rag_permission_filtering_enabled else None
        if effective_groups is None:
            chunks = self.retriever.retrieve_context(question, top_k or self.config.top_k)
        else:
            chunks = self.retriever.retrieve_context(question, top_k or self.config.top_k, allowed_groups=effective_groups)
        return RetrievalResult(
            chunks=chunks,
            diagnostics=_fallback_diagnostics(
                question_original,
                question,
                query_rewrite_used,
                chunks,
            ),
        )

    def _should_refuse_for_confidence(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        routing_profile: str | None,
    ) -> bool:
        if not self.config.rag_confidence_enabled or not chunks:
            return False
        if routing_profile == "global_summary" or _is_multi_document_question(question):
            return False
        best_score = chunks[0].score
        if best_score is not None and best_score < self.config.rag_min_confidence:
            return True
        if _question_is_vague(question) and len(chunks) > 1:
            second_score = chunks[1].score
            if best_score is not None and second_score is not None:
                return abs(best_score - second_score) < self.config.rag_low_confidence_margin
        return False

    def health(self) -> dict[str, object]:
        vector_available = self.vector_store.is_available()
        ollama_available = self.llm_client.is_available() and self.embedding_client.is_available()
        count = self.vector_store.count() if vector_available else None
        return {
            "ollama": ollama_available,
            "vector_store": vector_available,
            "collection_count": count,
        }

    def _format_context(self, chunks: list[RetrievedChunk]) -> str:
        blocks: list[str] = []
        total_chars = 0
        for index, chunk in enumerate(chunks, start=1):
            block = _format_context_block(index, chunk)
            if total_chars + len(block) > self.config.max_context_chars:
                break
            blocks.append(block)
            total_chars += len(block)
        return "\n\n---\n\n".join(blocks)


def _format_context_block(index: int, chunk: RetrievedChunk) -> str:
    file_name = chunk.metadata.get("file_name", "source inconnue")
    page = chunk.metadata.get("page")
    chunk_id = chunk.metadata.get("chunk_id", "")
    section_title = chunk.metadata.get("section_title")
    last_modified = chunk.metadata.get("last_modified") or chunk.metadata.get("indexed_at")
    score = f"{chunk.score:.3f}" if chunk.score is not None else "non disponible"
    page_line = f"page: {page}\n" if page not in (None, "") else ""
    section_line = f"section_title: {section_title}\n" if section_title not in (None, "") else ""
    version_line = f"last_modified_or_indexed_at: {last_modified}\n" if last_modified not in (None, "") else ""
    return (
        f"[Source {index}]\n"
        f"file_name: {file_name}\n"
        f"{page_line}"
        f"{section_line}"
        f"{version_line}"
        f"chunk_id: {chunk_id}\n"
        f"score: {score}\n"
        "excerpt:\n"
        f"{chunk.text.strip()}"
    )


def _select_chunks_for_profile(chunks: list[RetrievedChunk], routing_profile: str | None) -> list[RetrievedChunk]:
    if not chunks:
        return []

    if routing_profile == "global_summary":
        return _select_summary_chunks(chunks)

    expected_file = expected_file_for_profile(routing_profile)
    if expected_file:
        expected_chunks = [chunk for chunk in chunks if _file_name(chunk) == expected_file]
        if expected_chunks:
            return sorted(expected_chunks, key=lambda chunk: chunk.score or 0.0, reverse=True)[:3]
        return sorted(chunks, key=lambda chunk: chunk.score or 0.0, reverse=True)[:3]

    return sorted(chunks, key=lambda chunk: chunk.score or 0.0, reverse=True)


def _select_summary_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    selected: list[RetrievedChunk] = []
    seen_files: set[str] = set()
    for chunk in sorted(
        chunks,
        key=lambda item: (_summary_document_priority(item), item.score or 0.0),
        reverse=True,
    ):
        file_name = _file_name(chunk)
        if file_name in seen_files:
            continue
        selected.append(chunk)
        seen_files.add(file_name)
        if len(selected) >= 5:
            return selected
    if selected:
        return selected
    return sorted(chunks, key=lambda chunk: chunk.score or 0.0, reverse=True)[:5]


def _file_name(chunk: RetrievedChunk) -> str:
    return str(chunk.metadata.get("file_name", ""))


def _summary_document_priority(chunk: RetrievedChunk) -> int:
    file_name = normalize_text(_file_name(chunk))
    if any(marker in file_name for marker in ("procedure", "politique", "faq", "guide")):
        return 2
    return 0


def _filter_by_score_margin(chunks: list[RetrievedChunk], margin: float) -> list[RetrievedChunk]:
    scored = [chunk for chunk in chunks if chunk.score is not None]
    if not scored:
        return chunks
    best_score = max(chunk.score or 0.0 for chunk in scored)
    threshold = max(0.0, best_score - max(0.0, margin))
    return [chunk for chunk in chunks if chunk.score is None or chunk.score >= threshold]


def _source_from_chunk(chunk: RetrievedChunk) -> Source:
    page = chunk.metadata.get("page")
    return Source(
        file_name=str(chunk.metadata.get("file_name", "source inconnue")),
        page=str(page) if page not in (None, "") else None,
        chunk_id=str(chunk.metadata.get("chunk_id", "")),
        excerpt=_excerpt(chunk.text),
        score=chunk.score,
    )


def _ensure_sources_in_answer(answer: str, chunks: list[RetrievedChunk]) -> str:
    if "source" in answer.lower():
        return answer
    lines = ["", "Sources :"]
    for index, chunk in enumerate(chunks, start=1):
        file_name = chunk.metadata.get("file_name", "source inconnue")
        page = chunk.metadata.get("page")
        chunk_id = chunk.metadata.get("chunk_id", "")
        page_label = f", page {page}" if page else ""
        lines.append(f"{index}. {file_name}{page_label}, chunk {chunk_id}")
    return answer.rstrip() + "\n" + "\n".join(lines)


def _excerpt(text: str, max_length: int = 500) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 3].rstrip()}..."


def _fallback_diagnostics(
    question_original: str,
    question_rewritten: str,
    query_rewrite_used: bool,
    chunks: list[RetrievedChunk],
) -> RetrievalDiagnostics:
    return RetrievalDiagnostics(
        question_original=question_original,
        question_rewritten=question_rewritten,
        query_rewrite_used=query_rewrite_used,
        retrieval_mode="legacy",
        retrieved_chunks_initial=len(chunks),
        retrieved_chunks_final=len(chunks),
        confidence=round((chunks[0].score or 0.0) if chunks else 0.0, 4),
    )


def _question_is_vague(question: str) -> bool:
    normalized = normalize_text(question)
    return len(normalized.split()) <= 4 or any(
        marker in normalized
        for marker in ("et pour", "et si", "dans ce cas", "celui ci", "celle ci", "ce document")
    )


def _is_multi_document_question(question: str) -> bool:
    normalized = normalize_text(question)
    return any(
        marker in normalized
        for marker in ("resume", "synthese", "compare", "differences", "documents parlent", "procedures disponibles")
    )
