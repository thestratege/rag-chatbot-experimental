import pytest

from app.config import Settings
from app.llm_client import OllamaLLMClient, strip_internal_reasoning


class FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"message": {"content": self._content, "thinking": "raisonnement séparé"}}


class CaptureHttpClient:
    def __init__(self, captured: dict[str, object], content: str) -> None:
        self.captured = captured
        self.content = content

    def __enter__(self) -> "CaptureHttpClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, url: str, json: dict[str, object]) -> FakeResponse:
        self.captured["url"] = url
        self.captured["payload"] = json
        return FakeResponse(self.content)


def test_ollama_payload_disables_thinking_and_preserves_runtime_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    config = Settings(
        ollama_base_url="http://ollama.example.test:11434",
        ollama_llm_model="qwen3:14b",
        ollama_think=False,
        ollama_keep_alive="10m",
        ollama_num_ctx=8192,
        ollama_num_predict=512,
        ollama_temperature=0.1,
    )
    fake_client = CaptureHttpClient(captured, "<think>raisonnement privé</think>\n\n**Réponse finale**")
    monkeypatch.setattr("app.llm_client.httpx.Client", lambda timeout: fake_client)

    answer = OllamaLLMClient(config).generate_answer("Question", "Contexte documentaire")

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "qwen3:14b"
    assert payload["think"] is False
    assert payload["keep_alive"] == "10m"
    assert payload["options"] == {
        "temperature": 0.1,
        "num_ctx": 8192,
        "num_predict": 512,
    }
    assert answer == "**Réponse finale**"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<think>raisonnement privé</think>\nRéponse utile.", "Réponse utile."),
        ("thinking=raisonnement privé\nRéponse utile.", "Réponse utile."),
        ("Réponse utile.\n<think>raisonnement non terminé", "Réponse utile."),
    ],
)
def test_strip_internal_reasoning(raw: str, expected: str) -> None:
    assert strip_internal_reasoning(raw) == expected
