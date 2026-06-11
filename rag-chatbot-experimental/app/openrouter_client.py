from __future__ import annotations

import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.config import Settings, settings


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter cannot complete a request."""


class OpenRouterTimeoutError(OpenRouterError):
    """Raised when OpenRouter does not respond before the configured timeout."""


class OpenRouterHTTPError(OpenRouterError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_text: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class OpenRouterResponse:
    model_id: str
    content: str
    response_time_seconds: float
    raw_response: dict[str, Any]


class OpenRouterClient:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.base_url = config.openrouter_base_url
        self.api_key = config.openrouter_api_key
        self.timeout = httpx.Timeout(config.openrouter_timeout_seconds)

    def list_models(self) -> list[dict[str, Any]]:
        if not self.config.openrouter_enabled:
            raise OpenRouterError("OpenRouter est désactivé dans la configuration.")
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY est manquante dans .env.")

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(f"{self.base_url}/models", headers=self._headers())
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise OpenRouterTimeoutError(
                f"Timeout OpenRouter après {self.config.openrouter_timeout_seconds}s."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = _safe_response_text(exc.response)
            raise OpenRouterHTTPError(
                f"Erreur OpenRouter HTTP {exc.response.status_code}: {detail}",
                status_code=exc.response.status_code,
                response_text=detail,
                retry_after_seconds=_retry_after_seconds(exc.response),
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"Erreur réseau OpenRouter: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise OpenRouterError("OpenRouter a retourné une réponse JSON invalide.") from exc
        models = data.get("data", data)
        if not isinstance(models, list):
            raise OpenRouterError("OpenRouter a retourné une liste de modèles invalide.")
        return [model for model in models if isinstance(model, dict)]

    def chat_completion(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 700,
    ) -> OpenRouterResponse:
        if not self.config.openrouter_enabled:
            raise OpenRouterError("OpenRouter est désactivé dans la configuration.")
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY est manquante dans .env.")

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        started_at = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise OpenRouterTimeoutError(
                f"Timeout OpenRouter après {self.config.openrouter_timeout_seconds}s."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = _safe_response_text(exc.response)
            raise OpenRouterHTTPError(
                f"Erreur OpenRouter HTTP {exc.response.status_code}: {detail}",
                status_code=exc.response.status_code,
                response_text=detail,
                retry_after_seconds=_retry_after_seconds(exc.response),
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"Erreur réseau OpenRouter: {exc}") from exc

        elapsed = time.perf_counter() - started_at
        try:
            data = response.json()
        except ValueError as exc:
            raise OpenRouterError("OpenRouter a retourné une réponse JSON invalide.") from exc
        content = _extract_content(data)
        if not content:
            raise OpenRouterError("OpenRouter a retourné une réponse vide.")
        return OpenRouterResponse(
            model_id=model_id,
            content=content.strip(),
            response_time_seconds=elapsed,
            raw_response=data,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "rag-chatbot-experimental-benchmark",
            "X-OpenRouter-Title": "rag-chatbot-experimental-benchmark",
        }


def _extract_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return ""


def _safe_response_text(response: httpx.Response) -> str:
    text = response.text.strip()
    if not text:
        return response.reason_phrase
    try:
        data = response.json()
    except ValueError:
        return text[:1000]
    if isinstance(data, dict):
        data.pop("user_id", None)
        if isinstance(data.get("error"), dict):
            data["error"].pop("user_id", None)
        return json_dumps(data)[:1000]
    return text[:1000]


def _retry_after_seconds(response: httpx.Response) -> float | None:
    header_value = response.headers.get("Retry-After")
    header_delay = _parse_retry_after(header_value)
    if header_delay is not None:
        return header_delay
    try:
        data = response.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    metadata = data.get("error", {}).get("metadata", {}) if isinstance(data.get("error"), dict) else {}
    if not isinstance(metadata, dict):
        return None
    for key in ("retry_after_seconds", "retry_after_seconds_raw"):
        value = metadata.get(key)
        if isinstance(value, int | float):
            return float(value)
    nested_headers = metadata.get("headers")
    if isinstance(nested_headers, dict):
        return _parse_retry_after(str(nested_headers.get("Retry-After", "")))
    return None


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return max(0.0, float(cleaned))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(cleaned)
        except (TypeError, ValueError):
            return None
        return max(0.0, retry_at.timestamp() - time.time())


def json_dumps(data: Any) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
