from __future__ import annotations

import logging

import httpx

from app.config import Settings, settings
from app.schemas import DocumentChunk, EmbeddedChunk


logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when Ollama cannot generate embeddings."""


class OllamaEmbeddingClient:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.base_url = config.ollama_base_url
        self.model = config.ollama_embedding_model
        self.timeout = httpx.Timeout(config.request_timeout_seconds)
        if config.suppress_httpx_info_logs:
            logging.getLogger("httpx").setLevel(logging.WARNING)

    def embed_text(self, text: str) -> list[float]:
        embeddings = self.embed_texts([text])
        return embeddings[0]

    def embed_documents(self, chunks: list[DocumentChunk]) -> list[EmbeddedChunk]:
        if not chunks:
            return []
        texts = [chunk.text for chunk in chunks]
        vectors = self.embed_texts(texts)
        return [EmbeddedChunk(chunk=chunk, embedding=embedding) for chunk, embedding in zip(chunks, vectors, strict=True)]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        batch_size = self.config.embedding_batch_size
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": texts}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/api/embed", json=payload)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise EmbeddingError("Ollama est inaccessible. Vérifiez que `ollama serve` est démarré.") from exc
        except httpx.TimeoutException as exc:
            raise EmbeddingError("Timeout lors de la génération des embeddings avec Ollama.") from exc
        except httpx.HTTPStatusError as exc:
            detail = _safe_response_text(exc.response)
            raise EmbeddingError(
                f"Erreur Ollama embeddings. Le modèle `{self.model}` est-il installé ? Détail: {detail}"
            ) from exc

        data = response.json()
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or not vectors:
            raise EmbeddingError(f"Réponse embeddings invalide depuis Ollama pour le modèle `{self.model}`.")
        return [[float(value) for value in vector] for vector in vectors]

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
            return self.model_available()
        except Exception:
            return False

    def model_available(self) -> bool:
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
            models = response.json().get("models", [])
            return any(_model_name_matches(model.get("name", ""), self.model) for model in models)
        except Exception:
            return False


def _safe_response_text(response: httpx.Response) -> str:
    text = response.text.strip()
    return text[:500] if text else response.reason_phrase


def _model_name_matches(available: str, requested: str) -> bool:
    if available == requested:
        return True
    if ":" not in requested and available == f"{requested}:latest":
        return True
    return False


def embed_text(text: str) -> list[float]:
    return OllamaEmbeddingClient().embed_text(text)


def embed_documents(chunks: list[DocumentChunk]) -> list[EmbeddedChunk]:
    return OllamaEmbeddingClient().embed_documents(chunks)
