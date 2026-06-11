from __future__ import annotations

import logging
import re

import httpx

from app.config import Settings, settings


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un assistant documentaire interne.
Tu réponds uniquement à partir des extraits fournis.
Chaque affirmation factuelle doit être justifiée par ces extraits.
Si l'information n'est pas présente dans les extraits, réponds exactement :

Je ne trouve pas cette information dans les documents fournis.

Sources :
- Aucune source pertinente trouvée.

Tu ne dois pas inventer.
Tu dois répondre en français.
Tu dois être clair, concis et professionnel.
Tu dois mentionner les sources utilisées à la fin.
Si la question est trop vague pour choisir une information fiable, demande une précision.
Pour une procédure, structure la réponse en étapes.
Si plusieurs extraits se contredisent, signale clairement la contradiction sans la résoudre par supposition.
Mentionne la version, la date ou la section lorsqu'elle est fournie et utile.
Pour une synthèse multi-documents, structure la réponse par document ou thème.
N'affirme jamais avoir consulté un document qui n'apparaît pas dans les extraits.
Ne révèle jamais de raisonnement interne, de chaîne de pensée ou de contenu entre balises <think>.
N'affiche jamais de balise <think>.
"""


class LLMError(RuntimeError):
    """Raised when Ollama cannot generate an answer."""


class OllamaLLMClient:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.base_url = config.ollama_base_url
        self.model = config.ollama_llm_model
        self.timeout = httpx.Timeout(config.request_timeout_seconds)

    def generate_answer(self, question: str, context: str) -> str:
        if not question.strip():
            raise ValueError("La question ne peut pas être vide.")
        if not context.strip():
            return "Je ne trouve pas cette information dans les documents fournis."

        payload = {
            "model": self.model,
            "stream": False,
            "think": self.config.ollama_think,
            "keep_alive": self.config.ollama_keep_alive,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Extraits documentaires récupérés:\n"
                        f"{context}\n\n"
                        f"Question utilisateur :\n{question}\n\n"
                        "Réponds uniquement avec les informations présentes dans les extraits."
                    ),
                },
            ],
            "options": {
                "temperature": self.config.ollama_temperature,
                "num_ctx": self.config.ollama_num_ctx,
                "num_predict": self.config.ollama_num_predict,
            },
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise LLMError("Ollama est inaccessible. Vérifiez que `ollama serve` est démarré.") from exc
        except httpx.TimeoutException as exc:
            raise LLMError("Timeout lors de la génération de réponse avec Ollama.") from exc
        except httpx.HTTPStatusError as exc:
            detail = _safe_response_text(exc.response)
            raise LLMError(f"Erreur Ollama LLM. Le modèle `{self.model}` est-il installé ? Détail: {detail}") from exc

        data = response.json()
        answer = strip_internal_reasoning(data.get("message", {}).get("content", ""))
        if not answer:
            raise LLMError("Ollama a retourné une réponse vide.")
        return answer

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


def strip_internal_reasoning(text: str) -> str:
    """Remove accidental reasoning traces before returning model output."""
    cleaned = re.sub(r"(?is)<think\b[^>]*>.*?</think>", "", text)
    cleaned = re.sub(r"(?is)<think\b[^>]*>.*\Z", "", cleaned)
    cleaned = re.sub(r"(?im)^\s*thinking\s*[:=].*$", "", cleaned)
    return cleaned.strip()


def _model_name_matches(available: str, requested: str) -> bool:
    if available == requested:
        return True
    if ":" not in requested and available == f"{requested}:latest":
        return True
    return False
