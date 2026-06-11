from app.config import Settings
from app.retriever import Retriever
from app.schemas import RetrievedChunk


class FakeEmbeddingClient:
    def embed_text(self, text: str) -> list[float]:
        assert text == "Comment demander un accès ?"
        return [1.0, 0.0]


class FakeVectorStore:
    def query(self, embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        assert embedding == [1.0, 0.0]
        assert top_k == 2
        return [
            RetrievedChunk(
                text="La demande d'accès doit être validée par le gestionnaire.",
                metadata={"file_name": "procedure.txt", "chunk_id": "chunk-1", "page": None},
                score=0.82,
            ),
            RetrievedChunk(
                text="Passage trop peu pertinent.",
                metadata={"file_name": "autre.txt", "chunk_id": "chunk-2", "page": None},
                score=0.05,
            ),
        ]

    def add_chunks(self, chunks):  # type: ignore[no-untyped-def]
        return len(chunks)

    def reset(self) -> None:
        pass

    def count(self) -> int:
        return 2

    def is_available(self) -> bool:
        return True


def test_retriever_filters_by_similarity_threshold() -> None:
    config = Settings(retrieval_min_score=0.2)
    retriever = Retriever(config=config, embedding_client=FakeEmbeddingClient(), vector_store=FakeVectorStore())

    results = retriever.retrieve_context("Comment demander un accès ?", top_k=2)

    assert len(results) == 1
    assert results[0].metadata["file_name"] == "procedure.txt"

