from app.config import Settings
from app.hybrid_retriever import HybridRetriever, _fuse_results
from app.schemas import RetrievedChunk


class FakeEmbeddingClient:
    def embed_text(self, text: str) -> list[float]:
        return [1.0, 0.0]


class PermissionAwareStore:
    def __init__(self) -> None:
        self.public = RetrievedChunk(
            "La procédure ORION-LOCAL-742 décrit la demande d'accès.",
            {"chunk_id": "public-1", "file_name": "procedure_acces.txt", "allowed_groups": ["public"]},
            0.72,
        )
        self.restricted = RetrievedChunk(
            "La procédure ORION-LOCAL-742 réservée aux TI.",
            {"chunk_id": "ti-1", "file_name": "procedure_ti.txt", "allowed_groups": ["TI"]},
            0.95,
        )

    def query(self, embedding, top_k, allowed_groups=None):  # type: ignore[no-untyped-def]
        return [self.public] if allowed_groups == ("public",) else [self.restricted, self.public]

    def fetch_all(self, limit=None, allowed_groups=None):  # type: ignore[no-untyped-def]
        return [self.public] if allowed_groups == ("public",) else [self.public, self.restricted]


class SummaryStore:
    def __init__(self) -> None:
        self.chunks = [
            RetrievedChunk(
                "Expériences professionnelles du candidat.",
                {"chunk_id": "letter-1", "file_name": "lettre_presentation.pdf"},
                0.99,
            ),
            RetrievedChunk(
                "Procédure de demande d'accès.",
                {"chunk_id": "access-1", "file_name": "procedure_acces.txt"},
                0.55,
            ),
            RetrievedChunk(
                "Procédure de mot de passe.",
                {"chunk_id": "password-1", "file_name": "procedure_mot_de_passe.txt"},
                0.54,
            ),
            RetrievedChunk(
                "Procédure de création de rapport.",
                {"chunk_id": "report-1", "file_name": "procedure_creation_rapport.txt"},
                0.53,
            ),
        ]

    def query(self, embedding, top_k, allowed_groups=None):  # type: ignore[no-untyped-def]
        return self.chunks[:top_k]

    def fetch_all(self, limit=None, allowed_groups=None):  # type: ignore[no-untyped-def]
        return self.chunks[:limit] if limit else self.chunks


def test_hybrid_retriever_deduplicates_and_preserves_permissions() -> None:
    config = Settings(
        rag_hybrid_search_enabled=True,
        rag_rerank_enabled=False,
        rag_permission_filtering_enabled=True,
        rag_vector_top_k=12,
        rag_keyword_top_k=12,
        rag_final_top_k=5,
    )
    result = HybridRetriever(config, FakeEmbeddingClient(), PermissionAwareStore()).retrieve(
        "procédure ORION-LOCAL-742 accès",
        allowed_groups=("public",),
    )

    assert [chunk.metadata["chunk_id"] for chunk in result.chunks] == ["public-1"]
    assert result.diagnostics.retrieval_mode == "hybrid"
    assert result.diagnostics.retrieved_chunks_initial == 1
    assert result.chunks[0].metadata["retrieval_vector_score"] == 0.72
    assert result.chunks[0].metadata["retrieval_keyword_score"] > 0


def test_hybrid_retriever_open_mode_ignores_document_groups() -> None:
    config = Settings(
        rag_hybrid_search_enabled=True,
        rag_rerank_enabled=False,
        rag_permission_filtering_enabled=False,
        rag_final_top_k=5,
    )

    result = HybridRetriever(config, FakeEmbeddingClient(), PermissionAwareStore()).retrieve(
        "procédure ORION-LOCAL-742",
        allowed_groups=("public",),
    )

    assert {chunk.metadata["file_name"] for chunk in result.chunks} == {
        "procedure_acces.txt",
        "procedure_ti.txt",
    }


def test_hybrid_fusion_does_not_dilute_vector_only_result() -> None:
    chunk = RetrievedChunk(
        "Paraphrase sémantique sans terme exact.",
        {"chunk_id": "semantic-1", "file_name": "semantic.txt"},
        0.82,
    )

    fused = _fuse_results("question différente", [chunk], [], Settings())

    assert fused[0].score == 0.82


def test_hybrid_procedure_summary_deprioritizes_unrelated_letter() -> None:
    result = HybridRetriever(
        Settings(
            rag_hybrid_search_enabled=True,
            rag_rerank_enabled=True,
            rag_diversity_enabled=True,
            rag_final_top_k=3,
            rag_max_chunks_per_document=1,
        ),
        FakeEmbeddingClient(),
        SummaryStore(),
    ).retrieve("Résume les procédures disponibles.", final_top_k=3, diversity_enabled=True)

    assert {chunk.metadata["file_name"] for chunk in result.chunks} == {
        "procedure_acces.txt",
        "procedure_mot_de_passe.txt",
        "procedure_creation_rapport.txt",
    }
