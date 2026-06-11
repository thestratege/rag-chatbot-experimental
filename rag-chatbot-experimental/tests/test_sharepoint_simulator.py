import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from app import auth as auth_module
from app.auth import UserContext, effective_groups
from app.config import Settings
from app.rag_audit import RAGAuditLogger
from app.schemas import DocumentChunk, EmbeddedChunk, Source
from app.sharepoint_simulator import SharePointSimulator, SyncSummary
from app.vector_store import ChromaVectorStore


class FakeEmbeddingClient:
    def embed_documents(self, chunks: list[DocumentChunk]) -> list[EmbeddedChunk]:
        return [EmbeddedChunk(chunk=chunk, embedding=[1.0, 0.0]) for chunk in chunks]


class MemoryVectorStore:
    def __init__(self) -> None:
        self.chunks: dict[str, EmbeddedChunk] = {}

    def add_chunks(self, chunks: list[EmbeddedChunk]) -> int:
        self.chunks.update({chunk.chunk.chunk_id: chunk for chunk in chunks})
        return len(chunks)

    def delete_by_document_id(self, document_id: str) -> int:
        ids = [
            chunk_id
            for chunk_id, embedded in self.chunks.items()
            if embedded.chunk.metadata.get("document_id") == document_id
        ]
        for chunk_id in ids:
            self.chunks.pop(chunk_id)
        return len(ids)

    def count(self) -> int:
        return len(self.chunks)

    def reset(self) -> None:
        self.chunks.clear()

    def is_available(self) -> bool:
        return True


def simulator_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "sharepoint_simulator_enabled": True,
        "documents_dir": tmp_path / "documents",
        "chroma_persist_dir": tmp_path / "vector",
        "sharepoint_simulator_state_path": tmp_path / "index_state.json",
        "sharepoint_simulator_permissions_path": tmp_path / "permissions.json",
        "sharepoint_simulator_log_path": tmp_path / "simulator.log",
        "rag_audit_log_path": tmp_path / "rag.jsonl",
        "chunk_size": 160,
        "chunk_overlap": 20,
    }
    values.update(overrides)
    return Settings(**values)


def test_incremental_sync_detects_add_modify_delete_and_permissions(tmp_path: Path) -> None:
    config = simulator_settings(tmp_path)
    config.documents_dir.mkdir()
    (config.documents_dir / "public.txt").write_text("Version initiale publique.", encoding="utf-8")
    (config.documents_dir / "ti.txt").write_text("Procédure réservée à l'équipe TI.", encoding="utf-8")
    config.sharepoint_simulator_permissions_path.write_text('{"ti.txt": ["TI", "admin"]}', encoding="utf-8")
    store = MemoryVectorStore()
    simulator = SharePointSimulator(config, embedding_client=FakeEmbeddingClient(), vector_store=store)

    first = simulator.sync()
    assert first.added == 2
    assert first.chunks_added == 2
    assert {tuple(item.chunk.metadata["allowed_groups"]) for item in store.chunks.values()} == {
        ("public",),
        ("TI", "admin"),
    }

    unchanged = simulator.sync()
    assert unchanged.unchanged == 2
    assert unchanged.chunks_added == 0

    (config.documents_dir / "public.txt").write_text("Version publique modifiée avec une nouvelle règle.", encoding="utf-8")
    modified = simulator.sync()
    assert modified.modified == 1
    assert modified.unchanged == 1
    assert modified.chunks_deleted == 1
    assert modified.chunks_added == 1

    (config.documents_dir / "ti.txt").unlink()
    deleted = simulator.sync()
    assert deleted.deleted == 1
    assert deleted.chunks_deleted == 1
    assert all(item.chunk.metadata["file_name"] != "ti.txt" for item in store.chunks.values())
    deleted_document = next(document for document in simulator.documents() if document["file_name"] == "ti.txt")
    assert deleted_document["status"] == "deleted"


def test_modified_document_loses_old_chunks_when_reindexing_fails(tmp_path: Path) -> None:
    config = simulator_settings(tmp_path)
    config.documents_dir.mkdir()
    document = config.documents_dir / "public.txt"
    document.write_text("Version initiale.", encoding="utf-8")
    store = MemoryVectorStore()
    simulator = SharePointSimulator(config, embedding_client=FakeEmbeddingClient(), vector_store=store)
    simulator.sync()
    assert store.count() == 1

    class FailingEmbeddingClient:
        def embed_documents(self, chunks: list[DocumentChunk]) -> list[EmbeddedChunk]:
            raise RuntimeError("Embedding indisponible")

    document.write_text("Version modifiée.", encoding="utf-8")
    failing_simulator = SharePointSimulator(config, embedding_client=FailingEmbeddingClient(), vector_store=store)
    summary = failing_simulator.sync()

    assert summary.errors == 1
    assert summary.chunks_deleted == 1
    assert store.count() == 0


def test_chroma_filters_groups_and_deletes_by_document_id(tmp_path: Path) -> None:
    config = simulator_settings(tmp_path, collection_name="permission_test")
    store = ChromaVectorStore(config)
    store.add_chunks(
        [
            EmbeddedChunk(
                chunk=DocumentChunk(
                    text="Information publique",
                    metadata={
                        "chunk_id": "public-1",
                        "document_id": "public-doc",
                        "file_name": "public.txt",
                        "allowed_groups": ["public"],
                    },
                ),
                embedding=[1.0, 0.0],
            ),
            EmbeddedChunk(
                chunk=DocumentChunk(
                    text="Secret TI",
                    metadata={
                        "chunk_id": "ti-1",
                        "document_id": "ti-doc",
                        "file_name": "ti.txt",
                        "allowed_groups": ["TI", "admin"],
                    },
                ),
                embedding=[1.0, 0.0],
            ),
        ]
    )

    public_results = store.query([1.0, 0.0], top_k=5, allowed_groups=("public",))
    ti_results = store.query([1.0, 0.0], top_k=5, allowed_groups=("public", "TI"))

    assert [result.metadata["file_name"] for result in public_results] == ["public.txt"]
    assert {result.metadata["file_name"] for result in ti_results} == {"public.txt", "ti.txt"}
    assert store.delete_by_document_id("ti-doc") == 1
    assert store.count() == 1


def test_effective_groups_accepts_local_simulator_profiles_only() -> None:
    user = UserContext("anonymous_demo_user", "none", False, False, groups=("public",))
    simulator = Settings(environment="development", sharepoint_simulator_enabled=True)
    normal = Settings(environment="development", sharepoint_simulator_enabled=False)

    assert effective_groups(simulator, user, "demo-ti") == ("public", "TI")
    assert effective_groups(normal, user, "demo-ti") == ("public",)


def test_rag_audit_writes_jsonl_without_tokens(tmp_path: Path) -> None:
    config = simulator_settings(tmp_path, rag_audit_log_enabled=True)
    user = UserContext("demo-user", "mock", True, True, groups=("public",), roles=("demo",), token_present=True)

    RAGAuditLogger(config).write(
        question="Quelle procédure est disponible ?",
        provider="ollama",
        sources=[Source(file_name="public.txt", page=None, chunk_id="public-1", excerpt="Extrait", score=0.9)],
        response_time_ms=125,
        user_context=user,
        user_groups=("public",),
        answer="Une procédure est disponible.",
    )

    event = json.loads(config.rag_audit_log_path.read_text(encoding="utf-8"))
    assert event["user_id"] == "demo-user"
    assert event["sources"] == ["public.txt"]
    assert event["retrieved_chunks"] == 1
    assert event["question_original"] == "Quelle procédure est disponible ?"
    assert event["question_rewritten"] == "Quelle procédure est disponible ?"
    assert event["retrieval_mode"] == "unknown"
    assert event["confidence"] == 0.0
    assert event["permission_filtering_enabled"] is False
    assert "token" not in json.dumps(event).lower()


def test_admin_simulator_endpoints_require_admin_and_return_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = Settings(
        environment="demo",
        auth_enabled=True,
        auth_provider="mock",
        demo_auth_token="user-token",
        demo_admin_auth_token="admin-token",
        llm_provider="mock",
        sharepoint_simulator_enabled=True,
    )

    class FakeSimulator:
        def status(self) -> dict[str, object]:
            return {"document_count": 1, "chunk_count": 2}

        def documents(self) -> list[dict[str, object]]:
            return [{"document_id": "doc-1", "file_name": "public.txt", "status": "indexed"}]

        def sync(self) -> SyncSummary:
            return SyncSummary(added=1, chunks_added=2)

    monkeypatch.setattr(auth_module, "settings", config)
    monkeypatch.setattr(api_main, "settings", config)
    monkeypatch.setattr(api_main, "get_sharepoint_simulator", lambda: FakeSimulator())
    client = TestClient(api_main.app)

    assert client.get("/admin/index/status").status_code == 401
    assert client.get("/admin/index/status", headers={"Authorization": "Bearer user-token"}).status_code == 403
    admin_headers = {"Authorization": "Bearer admin-token"}
    status = client.get("/admin/index/status", headers=admin_headers).json()
    assert status["document_count"] == 1
    assert status["rag_diagnostics"]["permission_filtering_enabled"] is False
    assert client.get("/admin/index/documents", headers=admin_headers).json()[0]["file_name"] == "public.txt"
    assert client.post("/admin/index/sync", headers=admin_headers).json()["added"] == 1
