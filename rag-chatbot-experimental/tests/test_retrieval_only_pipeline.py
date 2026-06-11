import pytest

from app.config import Settings
from app.embeddings import OllamaEmbeddingClient
from app.openrouter_client import OpenRouterClient
from app.provider_router import ABSENT_WITH_SOURCES
from app.retrieval_only_pipeline import RetrievalOnlyPipeline
from app.schemas import RetrievedChunk


class FakeVectorStore:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks

    def add_chunks(self, chunks):  # type: ignore[no-untyped-def]
        return len(chunks)

    def query(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        raise AssertionError("retrieval_only ne doit pas appeler la recherche vectorielle par embedding")

    def fetch_all(
        self,
        limit: int | None = None,
        allowed_groups: tuple[str, ...] | None = None,
    ) -> list[RetrievedChunk]:
        chunks = self._chunks
        if allowed_groups is not None:
            chunks = [
                chunk
                for chunk in chunks
                if set(chunk.metadata.get("allowed_groups", ["public"])).intersection(allowed_groups)
            ]
        return chunks[:limit] if limit else chunks

    def reset(self) -> None:
        pass

    def count(self) -> int:
        return len(self._chunks)

    def is_available(self) -> bool:
        return True


def test_retrieval_only_returns_source_without_openrouter_or_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_ollama(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("retrieval_only ne doit pas contacter Ollama")

    def fail_openrouter(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("retrieval_only ne doit pas contacter OpenRouter")

    monkeypatch.setattr(OllamaEmbeddingClient, "embed_text", fail_ollama)
    monkeypatch.setattr(OpenRouterClient, "chat_completion", fail_openrouter)

    pipeline = RetrievalOnlyPipeline(
        config=Settings(llm_provider="retrieval_only", retrieval_min_score=0.1),
        vector_store=FakeVectorStore(
            [
                RetrievedChunk(
                    text=(
                        "Toute demande d'accès doit préciser le nom du demandeur, le service, "
                        "le rôle attendu et la justification opérationnelle."
                    ),
                    metadata={"file_name": "procedure_acces.txt", "chunk_id": "sample-acces-1", "page": None},
                )
            ]
        ),
    )

    response = pipeline.answer_question("comment demander un acces", top_k=3, routing_profile="access_request")

    assert response.answer.startswith("J’ai trouvé un passage pertinent dans le document procedure_acces.txt.")
    assert len(response.sources) == 1
    assert response.sources[0].file_name == "procedure_acces.txt"
    assert response.sources[0].chunk_id == "sample-acces-1"
    assert response.sources[0].score is not None


def test_retrieval_only_refuses_when_no_relevant_source() -> None:
    pipeline = RetrievalOnlyPipeline(
        config=Settings(llm_provider="retrieval_only", retrieval_min_score=0.3),
        vector_store=FakeVectorStore(
            [
                RetrievedChunk(
                    text="Le rapport mensuel inclut le périmètre et les indicateurs suivis.",
                    metadata={"file_name": "procedure_creation_rapport.txt", "chunk_id": "sample-report-1"},
                )
            ]
        ),
    )

    response = pipeline.answer_question("quelle est la politique de remboursement des billets d avion", top_k=3)

    assert response.answer == ABSENT_WITH_SOURCES
    assert response.sources == []


def test_retrieval_only_prioritizes_access_document_for_access_profile() -> None:
    pipeline = RetrievalOnlyPipeline(
        config=Settings(llm_provider="retrieval_only", retrieval_min_score=0.1),
        vector_store=FakeVectorStore(_sample_chunks()),
    )

    response = pipeline.answer_question("comment demander un acces", top_k=5, routing_profile="access_request")

    assert response.sources
    assert len(response.sources) <= 3
    assert response.sources[0].file_name == "procedure_acces.txt"
    assert response.answer.startswith("J’ai trouvé un passage pertinent dans le document procedure_acces.txt.")


def test_retrieval_only_prioritizes_password_document_for_password_profile() -> None:
    pipeline = RetrievalOnlyPipeline(
        config=Settings(llm_provider="retrieval_only", retrieval_min_score=0.1),
        vector_store=FakeVectorStore(_sample_chunks()),
    )

    response = pipeline.answer_question("mot de passe oublie", top_k=5, routing_profile="password_reset")

    assert response.sources
    assert len(response.sources) <= 3
    assert response.sources[0].file_name == "procedure_mot_de_passe.txt"


def test_retrieval_only_prioritizes_usage_policy_document_for_usage_profile() -> None:
    pipeline = RetrievalOnlyPipeline(
        config=Settings(llm_provider="retrieval_only", retrieval_min_score=0.1),
        vector_store=FakeVectorStore(_sample_chunks()),
    )

    response = pipeline.answer_question("bonnes pratiques utilisation", top_k=5, routing_profile="usage_policy")

    assert response.sources
    assert len(response.sources) <= 3
    assert response.sources[0].file_name == "politique_utilisation.txt"


def test_retrieval_only_global_summary_returns_multiple_documents() -> None:
    pipeline = RetrievalOnlyPipeline(
        config=Settings(llm_provider="retrieval_only", retrieval_min_score=0.1),
        vector_store=FakeVectorStore(_sample_chunks()),
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


def test_retrieval_only_unknown_documentary_refuses_exactly() -> None:
    pipeline = RetrievalOnlyPipeline(
        config=Settings(llm_provider="retrieval_only", retrieval_min_score=0.1),
        vector_store=FakeVectorStore(_sample_chunks()),
    )

    response = pipeline.answer_question(
        "quelle est la politique de remboursement des billets d avion",
        top_k=5,
        routing_profile="unknown_documentary",
    )

    assert response.answer == ABSENT_WITH_SOURCES
    assert response.sources == []


def test_retrieval_only_open_mode_returns_restricted_document_to_public_profile() -> None:
    restricted = RetrievedChunk(
        text="Le code de validation TI est ORION-LOCAL-742.",
        metadata={"file_name": "procedure_ti.txt", "chunk_id": "ti-1", "allowed_groups": ["TI"]},
    )
    pipeline = RetrievalOnlyPipeline(
        config=Settings(
            llm_provider="retrieval_only",
            retrieval_min_score=0.1,
            rag_permission_filtering_enabled=False,
        ),
        vector_store=FakeVectorStore([restricted]),
    )

    response = pipeline.answer_question(
        "Quel est le code ORION-LOCAL-742 ?",
        allowed_groups=("public",),
    )

    assert response.sources[0].file_name == "procedure_ti.txt"


def test_retrieval_only_filtered_mode_blocks_restricted_document_from_public_profile() -> None:
    restricted = RetrievedChunk(
        text="Le code de validation TI est ORION-LOCAL-742.",
        metadata={"file_name": "procedure_ti.txt", "chunk_id": "ti-1", "allowed_groups": ["TI"]},
    )
    pipeline = RetrievalOnlyPipeline(
        config=Settings(
            llm_provider="retrieval_only",
            retrieval_min_score=0.1,
            rag_permission_filtering_enabled=True,
        ),
        vector_store=FakeVectorStore([restricted]),
    )

    response = pipeline.answer_question(
        "Quel est le code ORION-LOCAL-742 ?",
        allowed_groups=("public",),
    )

    assert response.answer == ABSENT_WITH_SOURCES
    assert response.sources == []


def _sample_chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            text=(
                "Toute demande d'accès doit préciser le nom du demandeur, le service, le rôle attendu "
                "et la justification opérationnelle."
            ),
            metadata={"file_name": "procedure_acces.txt", "chunk_id": "sample-acces-1", "page": None},
        ),
        RetrievedChunk(
            text=(
                "Le support vérifie l'identité de l'utilisateur avant d'envoyer un lien temporaire "
                "de réinitialisation du mot de passe."
            ),
            metadata={"file_name": "procedure_mot_de_passe.txt", "chunk_id": "sample-password-1", "page": None},
        ),
        RetrievedChunk(
            text="Le rapport mensuel inclut le périmètre, la période et les indicateurs suivis.",
            metadata={"file_name": "procedure_creation_rapport.txt", "chunk_id": "sample-report-1", "page": None},
        ),
        RetrievedChunk(
            text="Le support traite les incidents, les demandes d'assistance et les problèmes techniques.",
            metadata={"file_name": "faq_support.txt", "chunk_id": "sample-support-1", "page": None},
        ),
        RetrievedChunk(
            text=(
                "Les bonnes pratiques d'utilisation consistent à utiliser les outils internes de manière "
                "responsable et à ne pas partager ses accès."
            ),
            metadata={"file_name": "politique_utilisation.txt", "chunk_id": "sample-policy-1", "page": None},
        ),
    ]
