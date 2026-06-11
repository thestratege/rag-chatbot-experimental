from __future__ import annotations

import logging
import os
import shutil
import json
from typing import Any, Protocol

from app.config import Settings, settings
from app.schemas import EmbeddedChunk, RetrievedChunk


os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
logger = logging.getLogger(__name__)
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)


class VectorStoreError(RuntimeError):
    """Raised when the vector store operation fails."""


class VectorStore(Protocol):
    def add_chunks(self, chunks: list[EmbeddedChunk]) -> int: ...

    def query(
        self,
        embedding: list[float],
        top_k: int,
        allowed_groups: tuple[str, ...] | None = None,
    ) -> list[RetrievedChunk]: ...

    def fetch_all(
        self,
        limit: int | None = None,
        allowed_groups: tuple[str, ...] | None = None,
    ) -> list[RetrievedChunk]: ...

    def delete_by_document_id(self, document_id: str) -> int: ...

    def reset(self) -> None: ...

    def count(self) -> int: ...

    def is_available(self) -> bool: ...


class ChromaVectorStore:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.persist_dir = config.chroma_persist_dir
        self.collection_name = config.collection_name
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._chromadb = self._import_chromadb()
        self.client = self._build_client()
        self.collection = self._get_or_create_collection()

    def _import_chromadb(self) -> Any:
        try:
            import chromadb
        except ImportError as exc:
            raise VectorStoreError("Le paquet `chromadb` est requis pour utiliser la base vectorielle.") from exc
        return chromadb

    def _build_client(self) -> Any:
        try:
            from chromadb.config import Settings as ChromaSettings

            chroma_settings = ChromaSettings(anonymized_telemetry=False)
            return self._chromadb.PersistentClient(path=str(self.persist_dir), settings=chroma_settings)
        except Exception:
            return self._chromadb.PersistentClient(path=str(self.persist_dir))

    def _get_or_create_collection(self) -> Any:
        return self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine", "description": "Documents internes pour chatbot RAG local"},
        )

    def add_chunks(self, chunks: list[EmbeddedChunk]) -> int:
        if not chunks:
            return 0
        try:
            self.collection.upsert(
                ids=[item.chunk.chunk_id for item in chunks],
                embeddings=[item.embedding for item in chunks],
                documents=[item.chunk.text for item in chunks],
                metadatas=[_sanitize_metadata(item.chunk.metadata) for item in chunks],
            )
            logger.info("%s chunk(s) indexé(s) dans Chroma.", len(chunks))
            return len(chunks)
        except Exception as exc:
            raise VectorStoreError(f"Impossible d'indexer les chunks dans Chroma: {exc}") from exc

    def query(
        self,
        embedding: list[float],
        top_k: int,
        allowed_groups: tuple[str, ...] | None = None,
    ) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        candidate_count = min(max(top_k * 10, top_k), self.count()) if allowed_groups is not None else min(top_k, self.count())
        try:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=candidate_count,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise VectorStoreError(f"Erreur lors de la recherche vectorielle: {exc}") from exc

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        retrieved: list[RetrievedChunk] = []
        for text, metadata, distance in zip(documents, metadatas, distances, strict=False):
            score = _distance_to_score(distance)
            restored = _restore_metadata(metadata or {})
            if _is_authorized(restored, allowed_groups):
                retrieved.append(RetrievedChunk(text=text, metadata=restored, score=score))
        return retrieved[:top_k]

    def fetch_all(
        self,
        limit: int | None = None,
        allowed_groups: tuple[str, ...] | None = None,
    ) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        try:
            kwargs: dict[str, object] = {"include": ["documents", "metadatas"]}
            if limit is not None and allowed_groups is None:
                kwargs["limit"] = limit
            results = self.collection.get(**kwargs)
        except Exception as exc:
            raise VectorStoreError(f"Erreur lors de la lecture des chunks Chroma: {exc}") from exc

        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])
        retrieved: list[RetrievedChunk] = []
        for text, metadata in zip(documents, metadatas, strict=False):
            restored = _restore_metadata(metadata or {})
            if _is_authorized(restored, allowed_groups):
                retrieved.append(RetrievedChunk(text=text, metadata=restored, score=None))
        return retrieved[:limit] if limit is not None else retrieved

    def delete_by_document_id(self, document_id: str) -> int:
        if not document_id or self.count() == 0:
            return 0
        try:
            existing = self.collection.get(where={"document_id": document_id}, include=[])
            ids = existing.get("ids", [])
            if ids:
                self.collection.delete(ids=ids)
            return len(ids)
        except Exception as exc:
            raise VectorStoreError(f"Impossible de supprimer le document `{document_id}` de Chroma: {exc}") from exc

    def reset(self) -> None:
        try:
            try:
                self.client.delete_collection(self.collection_name)
            except Exception:
                pass
            self.collection = self._get_or_create_collection()
        except Exception as exc:
            raise VectorStoreError(f"Impossible de réinitialiser la collection Chroma: {exc}") from exc

    def delete_persisted_store(self) -> None:
        self.reset()
        if self.persist_dir.exists():
            shutil.rmtree(self.persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = self._build_client()
        self.collection = self._get_or_create_collection()

    def count(self) -> int:
        try:
            return int(self.collection.count())
        except Exception as exc:
            raise VectorStoreError(f"Impossible de compter les documents dans Chroma: {exc}") from exc

    def is_available(self) -> bool:
        try:
            self.count()
            return True
        except Exception:
            return False


def build_vector_store(config: Settings = settings) -> VectorStore:
    if config.vector_db_type.lower() == "chroma":
        return ChromaVectorStore(config)
    raise VectorStoreError(f"Vector DB non supportée dans cette V1: {config.vector_db_type}")


def _sanitize_metadata(metadata: dict[str, object]) -> dict[str, str | int | float | bool]:
    sanitized: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if value is None:
            sanitized[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
        elif isinstance(value, (list, tuple, set)):
            sanitized[key] = json.dumps(list(value), ensure_ascii=False)
        else:
            sanitized[key] = str(value)
    return sanitized


def _restore_metadata(metadata: dict[str, object]) -> dict[str, object]:
    restored = dict(metadata)
    if restored.get("page") == "":
        restored["page"] = None
    raw_groups = restored.get("allowed_groups")
    if isinstance(raw_groups, str):
        try:
            parsed_groups = json.loads(raw_groups)
            if isinstance(parsed_groups, list):
                restored["allowed_groups"] = [str(group) for group in parsed_groups]
        except json.JSONDecodeError:
            restored["allowed_groups"] = [raw_groups]
    return restored


def _is_authorized(metadata: dict[str, object], user_groups: tuple[str, ...] | None) -> bool:
    if user_groups is None:
        return True
    raw_groups = metadata.get("allowed_groups", ["public"])
    if isinstance(raw_groups, str):
        document_groups = {raw_groups}
    elif isinstance(raw_groups, (list, tuple, set)):
        document_groups = {str(group) for group in raw_groups}
    else:
        document_groups = {"public"}
    return bool(document_groups.intersection(user_groups))


def _distance_to_score(distance: float | int | None) -> float | None:
    if distance is None:
        return None
    score = 1.0 - float(distance)
    return max(0.0, min(1.0, score))
