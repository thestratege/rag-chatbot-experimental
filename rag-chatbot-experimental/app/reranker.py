from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from app.intent_router import normalize_text
from app.schemas import RetrievedChunk


STOPWORDS = {
    "avec",
    "dans",
    "des",
    "document",
    "documents",
    "est",
    "les",
    "pour",
    "quel",
    "quelle",
    "quelles",
    "quels",
    "une",
}


@dataclass(frozen=True)
class RerankItem:
    chunk: RetrievedChunk
    debug: dict[str, object]


class HeuristicReranker:
    def rerank(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        *,
        top_k: int,
        diversity_enabled: bool = False,
        max_chunks_per_document: int = 2,
    ) -> list[RerankItem]:
        ranked = [self._score(question, chunk) for chunk in chunks]
        ranked.sort(key=lambda item: item.chunk.score or 0.0, reverse=True)
        if not diversity_enabled:
            return ranked[:top_k]

        selected: list[RerankItem] = []
        per_document: dict[str, int] = {}
        for item in ranked:
            file_name = str(item.chunk.metadata.get("file_name", "source inconnue"))
            if per_document.get(file_name, 0) >= max_chunks_per_document:
                continue
            selected.append(item)
            per_document[file_name] = per_document.get(file_name, 0) + 1
            if len(selected) >= top_k:
                break
        return selected

    def _score(self, question: str, chunk: RetrievedChunk) -> RerankItem:
        original_score = chunk.score or 0.0
        text_score, matched_terms = lexical_score(question, chunk.text)
        metadata_text = " ".join(
            str(chunk.metadata.get(key, ""))
            for key in ("file_name", "section_title", "page")
        )
        metadata_score, metadata_terms = lexical_score(question, metadata_text)
        exact_bonus = 0.08 if _contains_exact_phrase(question, chunk.text) else 0.0
        short_penalty = 0.08 if len(chunk.text.strip()) < 80 else 0.0
        rerank_score = min(
            1.0,
            max(
                0.0,
                (0.55 * original_score)
                + (0.30 * text_score)
                + (0.15 * metadata_score)
                + exact_bonus
                - short_penalty,
            ),
        )
        matched = sorted(set(matched_terms + metadata_terms))
        debug = {
            "chunk_id": str(chunk.metadata.get("chunk_id", "")),
            "original_score": round(original_score, 4),
            "rerank_score": round(rerank_score, 4),
            "matched_terms": matched,
            "reason": (
                f"vector={original_score:.3f}, lexical={text_score:.3f}, "
                f"metadata={metadata_score:.3f}, exact_bonus={exact_bonus:.2f}"
            ),
        }
        metadata = {**chunk.metadata, "rerank_debug": debug}
        return RerankItem(RetrievedChunk(chunk.text, metadata, round(rerank_score, 4)), debug)


def lexical_score(question: str, candidate: str) -> tuple[float, list[str]]:
    query_terms = _meaningful_terms(question)
    normalized_candidate = normalize_text(candidate)
    candidate_terms = set(normalized_candidate.split())
    if not query_terms or not candidate_terms:
        return 0.0, []
    matched = [term for term in query_terms if term in candidate_terms]
    exact_overlap = len(matched) / len(query_terms)
    fuzzy_matches = 0
    for term in query_terms:
        if term in candidate_terms:
            fuzzy_matches += 1
            continue
        if max((SequenceMatcher(None, term, other).ratio() for other in candidate_terms), default=0.0) >= 0.86:
            fuzzy_matches += 1
    fuzzy_overlap = fuzzy_matches / len(query_terms)
    return round((0.72 * exact_overlap) + (0.28 * fuzzy_overlap), 4), matched


def _meaningful_terms(text: str) -> list[str]:
    return [term for term in normalize_text(text).split() if len(term) > 2 and term not in STOPWORDS]


def _contains_exact_phrase(question: str, text: str) -> bool:
    normalized_text = normalize_text(text)
    terms = _meaningful_terms(question)
    return any(len(term) >= 5 and term in normalized_text for term in terms)
