from __future__ import annotations

from app.config import Settings, settings
from app.embeddings import OllamaEmbeddingClient
from app.intent_router import normalize_text
from app.reranker import HeuristicReranker, RerankItem, lexical_score
from app.schemas import RetrievalDiagnostics, RetrievalResult, RetrievedChunk
from app.vector_store import VectorStore, build_vector_store


class HybridRetriever:
    def __init__(
        self,
        config: Settings = settings,
        embedding_client: OllamaEmbeddingClient | None = None,
        vector_store: VectorStore | None = None,
        reranker: HeuristicReranker | None = None,
    ) -> None:
        self.config = config
        self.embedding_client = embedding_client or OllamaEmbeddingClient(config)
        self.vector_store = vector_store or build_vector_store(config)
        self.reranker = reranker or HeuristicReranker()

    def retrieve(
        self,
        question: str,
        *,
        final_top_k: int | None = None,
        allowed_groups: tuple[str, ...] | None = None,
        diversity_enabled: bool = False,
        question_original: str | None = None,
        query_rewrite_used: bool = False,
    ) -> RetrievalResult:
        effective_groups = allowed_groups if self.config.rag_permission_filtering_enabled else None
        requested_top_k = final_top_k or self.config.rag_final_top_k
        vector_chunks = self._vector_results(question, effective_groups, requested_top_k)
        keyword_chunks = self._keyword_results(question, effective_groups) if self.config.rag_hybrid_search_enabled else []
        fused = _fuse_results(question, vector_chunks, keyword_chunks, self.config)
        top_k = requested_top_k
        if self.config.rag_rerank_enabled:
            reranked = self.reranker.rerank(
                question,
                fused,
                top_k=len(fused) if diversity_enabled else min(top_k, self.config.rag_rerank_top_k),
            )
            if diversity_enabled and self.config.rag_diversity_enabled:
                reranked = _select_diverse_rerank_items(
                    question,
                    reranked,
                    top_k,
                    self.config.rag_max_chunks_per_document,
                )
            final_chunks = [item.chunk for item in reranked]
            debug = [item.debug for item in reranked]
        else:
            final_chunks = _apply_diversity(
                fused,
                top_k,
                self.config.rag_max_chunks_per_document if diversity_enabled else top_k,
            )
            debug = []
        confidence = (final_chunks[0].score or 0.0) if final_chunks else 0.0
        diagnostics = RetrievalDiagnostics(
            question_original=question_original or question,
            question_rewritten=question,
            query_rewrite_used=query_rewrite_used,
            retrieval_mode="hybrid" if self.config.rag_hybrid_search_enabled else "vector",
            retrieved_chunks_initial=len(fused),
            retrieved_chunks_final=len(final_chunks),
            confidence=round(confidence, 4),
            rerank_debug=debug,
        )
        return RetrievalResult(final_chunks, diagnostics)

    def _vector_results(
        self,
        question: str,
        allowed_groups: tuple[str, ...] | None,
        requested_top_k: int,
    ) -> list[RetrievedChunk]:
        embedding = self.embedding_client.embed_text(question)
        hybrid_capable = self.config.rag_hybrid_search_enabled and hasattr(self.vector_store, "fetch_all")
        top_k = self.config.rag_vector_top_k if hybrid_capable else requested_top_k
        if allowed_groups is None:
            return self.vector_store.query(embedding, top_k=top_k)
        return self.vector_store.query(embedding, top_k=top_k, allowed_groups=allowed_groups)

    def _keyword_results(
        self,
        question: str,
        allowed_groups: tuple[str, ...] | None,
    ) -> list[RetrievedChunk]:
        if not hasattr(self.vector_store, "fetch_all"):
            return []
        chunks = (
            self.vector_store.fetch_all()
            if allowed_groups is None
            else self.vector_store.fetch_all(allowed_groups=allowed_groups)
        )
        scored: list[RetrievedChunk] = []
        for chunk in chunks:
            metadata_text = " ".join(
                str(chunk.metadata.get(key, ""))
                for key in ("file_name", "section_title", "page")
            )
            text_score, _ = lexical_score(question, chunk.text)
            metadata_score, _ = lexical_score(question, metadata_text)
            score = min(1.0, (0.82 * text_score) + (0.18 * metadata_score))
            if score > 0:
                scored.append(RetrievedChunk(chunk.text, chunk.metadata, round(score, 4)))
        return sorted(scored, key=lambda chunk: chunk.score or 0.0, reverse=True)[: self.config.rag_keyword_top_k]


def _fuse_results(
    question: str,
    vector_chunks: list[RetrievedChunk],
    keyword_chunks: list[RetrievedChunk],
    config: Settings,
) -> list[RetrievedChunk]:
    candidates: dict[str, dict[str, object]] = {}
    for chunk in vector_chunks:
        key = _chunk_key(chunk)
        candidates[key] = {
            "chunk": chunk,
            "vector": chunk.score or 0.0,
            "keyword": 0.0,
            "has_vector": True,
            "has_keyword": False,
        }
    for chunk in keyword_chunks:
        key = _chunk_key(chunk)
        item = candidates.setdefault(
            key,
            {
                "chunk": chunk,
                "vector": 0.0,
                "keyword": 0.0,
                "has_vector": False,
                "has_keyword": False,
            },
        )
        item["keyword"] = chunk.score or 0.0
        item["has_keyword"] = True
    fused: list[RetrievedChunk] = []
    for item in candidates.values():
        chunk = item["chunk"]
        assert isinstance(chunk, RetrievedChunk)
        vector_score = float(item["vector"])
        keyword_score = float(item["keyword"])
        active_weight = (
            (config.rag_vector_weight if item["has_vector"] else 0.0)
            + (config.rag_keyword_weight if item["has_keyword"] else 0.0)
        )
        score = (
            (config.rag_vector_weight * vector_score) + (config.rag_keyword_weight * keyword_score)
        ) / active_weight
        metadata = {
            **chunk.metadata,
            "retrieval_vector_score": round(vector_score, 4),
            "retrieval_keyword_score": round(keyword_score, 4),
        }
        fused.append(RetrievedChunk(chunk.text, metadata, round(score, 4)))
    return sorted(fused, key=lambda chunk: chunk.score or 0.0, reverse=True)


def _apply_diversity(chunks: list[RetrievedChunk], top_k: int, max_per_document: int) -> list[RetrievedChunk]:
    selected: list[RetrievedChunk] = []
    counts: dict[str, int] = {}
    for chunk in chunks:
        file_name = str(chunk.metadata.get("file_name", "source inconnue"))
        if counts.get(file_name, 0) >= max_per_document:
            continue
        selected.append(chunk)
        counts[file_name] = counts.get(file_name, 0) + 1
        if len(selected) >= top_k:
            break
    return selected


def _select_diverse_rerank_items(
    question: str,
    items: list[RerankItem],
    top_k: int,
    max_per_document: int,
) -> list[RerankItem]:
    ordered = sorted(
        items,
        key=lambda item: (_document_category_priority(question, item.chunk), item.chunk.score or 0.0),
        reverse=True,
    )
    selected: list[RerankItem] = []
    counts: dict[str, int] = {}
    for item in ordered:
        file_name = str(item.chunk.metadata.get("file_name", "source inconnue"))
        if counts.get(file_name, 0) >= max_per_document:
            continue
        selected.append(item)
        counts[file_name] = counts.get(file_name, 0) + 1
        if len(selected) >= top_k:
            break
    return selected


def _document_category_priority(question: str, chunk: RetrievedChunk) -> int:
    normalized_question = normalize_text(question)
    if "procedure" not in normalized_question:
        return 0
    file_name = normalize_text(str(chunk.metadata.get("file_name", "")))
    return 2 if any(marker in file_name for marker in ("procedure", "politique", "faq", "guide")) else 0


def _chunk_key(chunk: RetrievedChunk) -> str:
    return str(chunk.metadata.get("chunk_id") or f"{chunk.metadata.get('file_name')}:{chunk.text[:80]}")
