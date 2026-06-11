from app.reranker import HeuristicReranker
from app.schemas import RetrievedChunk


def test_reranker_prioritizes_exact_terms_and_returns_debug() -> None:
    chunks = [
        RetrievedChunk(
            "Information générale sur les outils.",
            {"chunk_id": "generic", "file_name": "general.txt"},
            0.75,
        ),
        RetrievedChunk(
            "La procédure ORION-LOCAL-742 décrit les accès SharePoint.",
            {"chunk_id": "exact", "file_name": "procedure_orion.txt", "section_title": "ORION-LOCAL-742"},
            0.60,
        ),
    ]

    ranked = HeuristicReranker().rerank("ORION-LOCAL-742 accès SharePoint", chunks, top_k=2)

    assert ranked[0].chunk.metadata["chunk_id"] == "exact"
    assert ranked[0].debug["matched_terms"]
    assert "vector=" in str(ranked[0].debug["reason"])


def test_reranker_diversifies_documents() -> None:
    chunks = [
        RetrievedChunk("Procédure accès A", {"chunk_id": "a1", "file_name": "a.txt"}, 0.9),
        RetrievedChunk("Procédure accès A suite", {"chunk_id": "a2", "file_name": "a.txt"}, 0.8),
        RetrievedChunk("Procédure accès B", {"chunk_id": "b1", "file_name": "b.txt"}, 0.7),
    ]

    ranked = HeuristicReranker().rerank(
        "procédure accès",
        chunks,
        top_k=2,
        diversity_enabled=True,
        max_chunks_per_document=1,
    )

    assert {item.chunk.metadata["file_name"] for item in ranked} == {"a.txt", "b.txt"}
