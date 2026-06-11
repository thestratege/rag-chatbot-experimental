from __future__ import annotations

from difflib import SequenceMatcher

from app.config import Settings, settings
from app.document_routing import PROFILE_TO_PRIMARY_FILE, SUMMARY_FILES
from app.intent_router import normalize_text
from app.provider_router import ABSENT_WITH_SOURCES
from app.schemas import ChatResponse, RetrievedChunk, Source
from app.vector_store import VectorStore, build_vector_store


STOPWORDS = {
    "a",
    "au",
    "aux",
    "ce",
    "ces",
    "comment",
    "dans",
    "de",
    "des",
    "du",
    "est",
    "et",
    "la",
    "le",
    "les",
    "pour",
    "qu",
    "que",
    "quel",
    "quelle",
    "quelles",
    "quels",
    "sur",
    "un",
    "une",
}

class RetrievalOnlyPipeline:
    """Retrieval-only answer builder that never calls an LLM or embedding model."""

    def __init__(self, config: Settings = settings, vector_store: VectorStore | None = None) -> None:
        self.config = config
        self.vector_store = vector_store or build_vector_store(config)

    def answer_question(
        self,
        question: str,
        top_k: int | None = None,
        routing_profile: str | None = None,
        allowed_groups: tuple[str, ...] | None = None,
    ) -> ChatResponse:
        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("La question ne peut pas être vide.")

        if routing_profile == "unknown_documentary":
            return ChatResponse(answer=ABSENT_WITH_SOURCES, sources=[])

        effective_top_k = _effective_top_k(top_k or self.config.top_k, routing_profile)
        chunks = self._retrieve(cleaned_question, effective_top_k, routing_profile, allowed_groups)
        if not chunks:
            return ChatResponse(answer=ABSENT_WITH_SOURCES, sources=[])

        sources = [_source_from_chunk(chunk) for chunk in chunks]
        answer = _format_retrieval_only_answer(chunks, routing_profile)
        return ChatResponse(answer=answer, sources=sources)

    def _retrieve(
        self,
        question: str,
        top_k: int,
        routing_profile: str | None = None,
        allowed_groups: tuple[str, ...] | None = None,
    ) -> list[RetrievedChunk]:
        if not self.vector_store.is_available() or self.vector_store.count() == 0:
            return []
        effective_groups = allowed_groups if self.config.rag_permission_filtering_enabled else None
        chunks = (
            self.vector_store.fetch_all()
            if effective_groups is None
            else self.vector_store.fetch_all(allowed_groups=effective_groups)
        )
        scored = [
            RetrievedChunk(text=chunk.text, metadata=chunk.metadata, score=_lexical_score(question, chunk.text))
            for chunk in chunks
        ]

        if routing_profile == "global_summary":
            return _select_global_summary_chunks(scored, top_k)

        expected_file = PROFILE_TO_PRIMARY_FILE.get(routing_profile or "")
        if expected_file:
            expected_chunks = [
                _boost_chunk(chunk)
                for chunk in scored
                if _file_name(chunk) == expected_file
                and chunk.score is not None
                and chunk.score >= self.config.retrieval_min_score
            ]
            if expected_chunks:
                return sorted(expected_chunks, key=lambda chunk: chunk.score or 0.0, reverse=True)[:top_k]

        filtered = [chunk for chunk in scored if chunk.score is not None and chunk.score >= self.config.retrieval_min_score]
        return sorted(filtered, key=lambda chunk: chunk.score or 0.0, reverse=True)[:top_k]


def _lexical_score(question: str, text: str) -> float:
    normalized_question = normalize_text(question)
    normalized_text = normalize_text(text)
    question_terms = {term for term in normalized_question.split() if term not in STOPWORDS and len(term) > 2}
    text_terms = set(normalized_text.split())
    if not question_terms or not normalized_text:
        return 0.0

    exact_overlap = len(question_terms.intersection(text_terms)) / len(question_terms)
    fuzzy_overlap = _fuzzy_overlap(question_terms, text_terms)
    sequence_score = SequenceMatcher(None, normalized_question, normalized_text[:1000]).ratio()
    return round(min(1.0, (0.55 * exact_overlap) + (0.35 * fuzzy_overlap) + (0.10 * sequence_score)), 3)


def _fuzzy_overlap(question_terms: set[str], text_terms: set[str]) -> float:
    if not question_terms or not text_terms:
        return 0.0
    matched = 0
    for question_term in question_terms:
        best = max(SequenceMatcher(None, question_term, text_term).ratio() for text_term in text_terms)
        if best >= 0.82:
            matched += 1
    return matched / len(question_terms)


def _effective_top_k(top_k: int, routing_profile: str | None) -> int:
    if routing_profile == "global_summary":
        return min(max(top_k, 5), 5)
    return min(top_k, 3)


def _select_global_summary_chunks(chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
    selected: list[RetrievedChunk] = []
    for file_name in SUMMARY_FILES:
        candidates = [chunk for chunk in chunks if _file_name(chunk) == file_name]
        if not candidates:
            continue
        selected.append(_boost_chunk(max(candidates, key=lambda chunk: chunk.score or 0.0), amount=0.15))
        if len(selected) >= top_k:
            return selected
    if selected:
        return selected
    return sorted(chunks, key=lambda chunk: chunk.score or 0.0, reverse=True)[:top_k]


def _boost_chunk(chunk: RetrievedChunk, amount: float = 0.35) -> RetrievedChunk:
    score = min(1.0, (chunk.score or 0.0) + amount)
    return RetrievedChunk(text=chunk.text, metadata=chunk.metadata, score=round(score, 3))


def _file_name(chunk: RetrievedChunk) -> str:
    return str(chunk.metadata.get("file_name", ""))


def _format_retrieval_only_answer(chunks: list[RetrievedChunk], routing_profile: str | None = None) -> str:
    first_file = _file_name(chunks[0]) if chunks else "source inconnue"
    if routing_profile in PROFILE_TO_PRIMARY_FILE and len(chunks) == 1:
        lines = [f"J’ai trouvé un passage pertinent dans le document {first_file}.", "", "Extrait pertinent :"]
    elif routing_profile in PROFILE_TO_PRIMARY_FILE:
        lines = [f"J’ai trouvé des passages pertinents dans le document {first_file}.", "", "Extraits pertinents :"]
    else:
        lines = [
            "J’ai trouvé les passages suivants dans les documents disponibles. Voici les éléments pertinents :",
            "",
        ]
    for index, chunk in enumerate(chunks, start=1):
        lines.append(f"{index}. {_excerpt(chunk.text, 360)}")
    lines.append("")
    lines.append("Sources :")
    for chunk in chunks:
        file_name = chunk.metadata.get("file_name", "source inconnue")
        page = chunk.metadata.get("page")
        chunk_id = chunk.metadata.get("chunk_id", "")
        score = f", score {chunk.score:.2f}" if chunk.score is not None else ""
        page_label = f", page {page}" if page not in (None, "") else ""
        lines.append(f"- {file_name}{page_label}, chunk {chunk_id}{score}")
    return "\n".join(lines)


def _source_from_chunk(chunk: RetrievedChunk) -> Source:
    page = chunk.metadata.get("page")
    return Source(
        file_name=str(chunk.metadata.get("file_name", "source inconnue")),
        page=str(page) if page not in (None, "") else None,
        chunk_id=str(chunk.metadata.get("chunk_id", "")),
        excerpt=_excerpt(chunk.text),
        score=chunk.score,
    )


def _excerpt(text: str, max_length: int = 500) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 3].rstrip()}..."
