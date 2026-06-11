from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.config import Settings, settings
from app.intent_router import normalize_text
from app.llm_client import strip_internal_reasoning
from app.schemas import QueryRewriteResult


logger = logging.getLogger(__name__)


class QueryRewriteClient(Protocol):
    def rewrite(self, question: str, history: list[str]) -> str: ...


class OllamaQueryRewriteClient:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    def rewrite(self, question: str, history: list[str]) -> str:
        history_text = "\n".join(f"- {message}" for message in history[-4:]) or "- Aucun contexte conversationnel."
        payload = {
            "model": self.config.ollama_llm_model,
            "stream": False,
            "think": False,
            "keep_alive": self.config.ollama_keep_alive,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Tu reformules une question documentaire pour améliorer la recherche. "
                        "Retourne uniquement une question autonome en français. N'y réponds pas. "
                        "N'ajoute aucun fait absent de la question ou de l'historique."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Historique récent:\n{history_text}\n\nQuestion à reformuler:\n{question}",
                },
            ],
            "options": {
                "temperature": 0,
                "num_predict": self.config.rag_query_rewrite_max_tokens,
            },
        }
        with httpx.Client(timeout=self.config.request_timeout_seconds) as client:
            response = client.post(f"{self.config.ollama_base_url}/api/chat", json=payload)
            response.raise_for_status()
        return strip_internal_reasoning(response.json().get("message", {}).get("content", "")).strip()


class QueryRewriter:
    def __init__(
        self,
        config: Settings = settings,
        client: QueryRewriteClient | None = None,
    ) -> None:
        self.config = config
        self.client = client or OllamaQueryRewriteClient(config)

    def rewrite(self, question: str, history: list[str] | None = None) -> QueryRewriteResult:
        original = question.strip()
        recent_history = [message.strip() for message in (history or []) if message.strip()]
        if not self.config.rag_query_rewrite_enabled:
            return QueryRewriteResult(original, original, False, "Reformulation désactivée.")
        if not _needs_rewrite(original, recent_history):
            return QueryRewriteResult(original, original, False, "Question déjà autonome.")
        try:
            rewritten = self.client.rewrite(original, recent_history).strip().strip('"')
            if not rewritten or len(rewritten) > 600:
                raise ValueError("Reformulation vide ou trop longue.")
            return QueryRewriteResult(original, rewritten, rewritten != original, "Question contextuelle reformulée.")
        except Exception as exc:
            logger.warning("Échec de reformulation; utilisation de la question originale: %s", exc)
            return QueryRewriteResult(original, original, False, "Échec de reformulation; fallback original.")


def _needs_rewrite(question: str, history: list[str]) -> bool:
    if not history:
        return False
    normalized = normalize_text(question)
    contextual_markers = (
        "et pour",
        "et si",
        "dans ce cas",
        "celui ci",
        "celle ci",
        "cette procedure",
        "ce document",
        "a ce sujet",
    )
    vague_references = {"cela", "ceci", "celui", "celle", "eux", "elles", "lui"}
    terms = set(normalized.split())
    return any(marker in normalized for marker in contextual_markers) or (
        len(terms) <= 5 and bool(terms.intersection(vague_references))
    )
