from __future__ import annotations

from app.config import Settings, settings
from app.embeddings import OllamaEmbeddingClient
from app.hybrid_retriever import HybridRetriever
from app.schemas import RetrievalDiagnostics, RetrievalResult, RetrievedChunk
from app.vector_store import VectorStore, build_vector_store


class Retriever:
    def __init__(
        self,
        config: Settings = settings,
        embedding_client: OllamaEmbeddingClient | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.config = config
        self.embedding_client = embedding_client or OllamaEmbeddingClient(config)
        self.vector_store = vector_store or build_vector_store(config)
        self.hybrid_retriever = HybridRetriever(config, self.embedding_client, self.vector_store)

    def retrieve_with_diagnostics(
        self,
        question: str,
        top_k: int | None = None,
        allowed_groups: tuple[str, ...] | None = None,
        *,
        diversity_enabled: bool = False,
        question_original: str | None = None,
        query_rewrite_used: bool = False,
    ) -> RetrievalResult:
        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("La question ne peut pas être vide.")

        effective_groups = allowed_groups if self.config.rag_permission_filtering_enabled else None
        result = self.hybrid_retriever.retrieve(
            cleaned_question,
            final_top_k=top_k or self.config.rag_final_top_k,
            allowed_groups=effective_groups,
            diversity_enabled=diversity_enabled,
            question_original=question_original,
            query_rewrite_used=query_rewrite_used,
        )
        threshold = self.config.retrieval_min_score
        chunks = [chunk for chunk in result.chunks if chunk.score is None or chunk.score >= threshold]
        diagnostics = RetrievalDiagnostics(
            **{
                **result.diagnostics.__dict__,
                "retrieved_chunks_final": len(chunks),
                "confidence": round((chunks[0].score or 0.0) if chunks else 0.0, 4),
            }
        )
        return RetrievalResult(chunks=chunks, diagnostics=diagnostics)

    def retrieve_context(
        self,
        question: str,
        top_k: int | None = None,
        allowed_groups: tuple[str, ...] | None = None,
    ) -> list[RetrievedChunk]:
        return self.retrieve_with_diagnostics(
            question,
            top_k=top_k,
            allowed_groups=allowed_groups,
        ).chunks


def retrieve_context(
    question: str,
    top_k: int = 5,
    allowed_groups: tuple[str, ...] | None = None,
) -> list[RetrievedChunk]:
    return Retriever().retrieve_context(question, top_k=top_k, allowed_groups=allowed_groups)
