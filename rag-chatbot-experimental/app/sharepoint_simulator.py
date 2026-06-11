from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.chunker import TextChunker
from app.config import Settings, settings
from app.document_loader import DocumentLoader, SUPPORTED_EXTENSIONS
from app.embeddings import OllamaEmbeddingClient
from app.schemas import DocumentPart
from app.vector_store import VectorStore, build_vector_store


logger = logging.getLogger(__name__)


@dataclass
class SyncSummary:
    added: int = 0
    modified: int = 0
    deleted: int = 0
    unchanged: int = 0
    chunks_added: int = 0
    chunks_deleted: int = 0
    errors: int = 0


class SharePointSimulator:
    """Incremental local document library used only for the SharePoint POC."""

    def __init__(
        self,
        config: Settings = settings,
        loader: DocumentLoader | None = None,
        chunker: TextChunker | None = None,
        embedding_client: OllamaEmbeddingClient | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.config = config
        self.documents_dir = config.documents_dir
        self.state_path = config.sharepoint_simulator_state_path
        self.permissions_path = config.sharepoint_simulator_permissions_path
        self.log_path = config.sharepoint_simulator_log_path
        self.loader = loader or DocumentLoader(self.documents_dir)
        self.chunker = chunker or TextChunker(config.chunk_size, config.chunk_overlap)
        self.embedding_client = embedding_client or OllamaEmbeddingClient(config)
        self.vector_store = vector_store or build_vector_store(config)

    def sync(self) -> SyncSummary:
        self._ensure_directories()
        state = self._read_state()
        state_documents = state.setdefault("documents", {})
        permissions = self._read_permissions()
        current_ids: set[str] = set()
        summary = SyncSummary()

        for path in self._iter_documents():
            relative_path = str(path.relative_to(self.documents_dir))
            document_id = _document_id(relative_path)
            current_ids.add(document_id)
            file_hash = _file_hash(path)
            previous = state_documents.get(document_id)
            allowed_groups = permissions.get(relative_path, permissions.get(path.name, ["public"]))
            if (
                previous
                and previous.get("file_hash") == file_hash
                and previous.get("allowed_groups") == allowed_groups
                and previous.get("status") == "indexed"
            ):
                summary.unchanged += 1
                continue

            is_modified = bool(previous and previous.get("status") != "deleted")
            indexed_at = _now()
            if is_modified:
                summary.chunks_deleted += self.vector_store.delete_by_document_id(document_id)
            try:
                parts = self.loader.load_file(path)
                enriched_parts = [
                    DocumentPart(
                        text=part.text,
                        metadata={
                            **part.metadata,
                            "document_id": document_id,
                            "file_path": relative_path,
                            "source_type": path.suffix.lower().lstrip("."),
                            "file_hash": file_hash,
                            "indexed_at": indexed_at,
                            "allowed_groups": allowed_groups,
                        },
                    )
                    for part in parts
                ]
                chunks = self.chunker.chunk_documents(enriched_parts)
                embedded_chunks = self.embedding_client.embed_documents(chunks)
                summary.chunks_added += self.vector_store.add_chunks(embedded_chunks)
                state_documents[document_id] = {
                    "document_id": document_id,
                    "file_path": relative_path,
                    "file_name": path.name,
                    "source_type": path.suffix.lower().lstrip("."),
                    "file_hash": file_hash,
                    "last_modified": _modified_at(path),
                    "indexed_at": indexed_at,
                    "chunk_count": len(chunks),
                    "status": "indexed",
                    "allowed_groups": allowed_groups,
                    "error": None,
                }
                if is_modified:
                    summary.modified += 1
                else:
                    summary.added += 1
            except Exception as exc:
                logger.warning("Erreur de synchronisation pour %s: %s", relative_path, exc)
                summary.errors += 1
                state_documents[document_id] = {
                    "document_id": document_id,
                    "file_path": relative_path,
                    "file_name": path.name,
                    "source_type": path.suffix.lower().lstrip("."),
                    "file_hash": file_hash,
                    "last_modified": _modified_at(path),
                    "indexed_at": previous.get("indexed_at") if previous else None,
                    "chunk_count": 0 if is_modified else (previous.get("chunk_count", 0) if previous else 0),
                    "status": "error",
                    "allowed_groups": allowed_groups,
                    "error": str(exc)[:500],
                }

        for document_id, document in list(state_documents.items()):
            if document_id in current_ids or document.get("status") == "deleted":
                continue
            summary.chunks_deleted += self.vector_store.delete_by_document_id(document_id)
            document.update(
                {
                    "status": "deleted",
                    "chunk_count": 0,
                    "deleted_at": _now(),
                    "error": None,
                }
            )
            summary.deleted += 1

        state["last_sync_at"] = _now()
        state["last_sync_summary"] = asdict(summary)
        self._write_state(state)
        self._append_sync_log(summary)
        return summary

    def status(self) -> dict[str, object]:
        state = self._read_state()
        documents = self.documents()
        return {
            "vector_store": _display_path(self.config.chroma_persist_dir),
            "documents_dir": _display_path(self.documents_dir),
            "document_count": sum(document["status"] == "indexed" for document in documents),
            "chunk_count": self.vector_store.count(),
            "last_sync_at": state.get("last_sync_at"),
            "last_sync_summary": state.get("last_sync_summary", asdict(SyncSummary())),
            "provider": self.config.llm_provider,
            "llm_model": self.config.ollama_llm_model,
            "embedding_model": self.config.ollama_embedding_model,
        }

    def documents(self) -> list[dict[str, Any]]:
        state_documents = self._read_state().get("documents", {})
        return sorted(state_documents.values(), key=lambda item: str(item.get("file_name", "")).lower())

    def reset(self) -> dict[str, int]:
        if not self.config.sharepoint_simulator_enabled:
            raise RuntimeError("Le reset est réservé au backend du simulateur SharePoint.")
        removed_chunks = self.vector_store.count()
        self.vector_store.reset()
        self._write_state({"last_sync_at": _now(), "last_sync_summary": asdict(SyncSummary()), "documents": {}})
        self._append_line("Reset de l'index simulateur.")
        return {"chunks_removed": removed_chunks}

    def _iter_documents(self) -> list[Path]:
        if not self.documents_dir.exists():
            return []
        return sorted(
            path
            for path in self.documents_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"last_sync_at": None, "last_sync_summary": asdict(SyncSummary()), "documents": {}}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"documents": {}}
        except (json.JSONDecodeError, OSError):
            logger.warning("État simulateur illisible; un nouvel état sera créé.")
            return {"last_sync_at": None, "last_sync_summary": asdict(SyncSummary()), "documents": {}}

    def _write_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.state_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary_path.replace(self.state_path)

    def _read_permissions(self) -> dict[str, list[str]]:
        if not self.permissions_path.exists():
            return {}
        try:
            raw = json.loads(self.permissions_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Le fichier de permissions du simulateur est invalide: {exc}") from exc
        if not isinstance(raw, dict):
            raise RuntimeError("Le fichier de permissions doit contenir un objet JSON.")
        permissions: dict[str, list[str]] = {}
        for file_name, groups in raw.items():
            if isinstance(groups, list) and groups:
                permissions[str(file_name)] = [str(group) for group in groups]
        return permissions

    def _ensure_directories(self) -> None:
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _append_sync_log(self, summary: SyncSummary) -> None:
        self._append_line(
            "Synchronisation: "
            f"ajoutés={summary.added}, modifiés={summary.modified}, supprimés={summary.deleted}, "
            f"inchangés={summary.unchanged}, chunks_ajoutés={summary.chunks_added}, "
            f"chunks_supprimés={summary.chunks_deleted}, erreurs={summary.errors}"
        )

    def _append_line(self, message: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{_now()} {message}\n")


def _document_id(relative_path: str) -> str:
    return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:24]


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as document:
        for block in iter(lambda: document.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _modified_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path(__file__).resolve().parents[1]))
    except ValueError:
        return str(path)
