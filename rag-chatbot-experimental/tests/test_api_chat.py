import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from app.config import Settings
from app.conversation_manager import ConversationManager
from app.llm_client import LLMError
from app.provider_router import ABSENT_WITH_SOURCES, CAPABILITY_ANSWER, ProviderRouter
from app.rag_pipeline import NOT_FOUND_ANSWER
from app.schemas import ChatResponse, Source


@pytest.fixture(autouse=True)
def force_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_main, "provider_router", ProviderRouter(Settings(llm_provider="mock")))
    monkeypatch.setattr(api_main, "conversation_manager", ConversationManager(history_limit=10))


def test_api_chat_greeting_does_not_trigger_rag() -> None:
    client = TestClient(api_main.app)

    response = client.post("/api/chat", json={"conversation_id": None, "message": "Bonjour", "mode": "auto"})

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "greeting"
    assert data["used_rag"] is False
    assert data["provider"] == "mock"
    assert data["sources"] == []


@pytest.mark.parametrize(
    "message",
    [
        "Je veux comprendre comment tu peux m’aider.",
        "Je veux comprendre comment tu peux m'aider.",
    ],
)
def test_api_chat_capability_question_does_not_trigger_rag(message: str) -> None:
    client = TestClient(api_main.app)

    response = client.post("/api/chat", json={"conversation_id": None, "message": message, "mode": "auto"})

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == CAPABILITY_ANSWER
    assert data["intent"] == "capability_question"
    assert data["routing_profile"] == "capability_question"
    assert data["used_rag"] is False
    assert data["provider"] == "mock"
    assert data["sources"] == []


def test_api_chat_documentary_question_returns_sources() -> None:
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={"conversation_id": None, "message": "Quelle est la procédure de demande d'accès ?", "mode": "auto"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "rag_question"
    assert data["routing_profile"] == "access_request"
    assert data["used_rag"] is True
    assert data["sources"][0]["file_name"] == "procedure_acces.txt"
    assert data["sources"][0]["chunk_id"] == "sample-acces-1"
    assert "Sources :" in data["answer"]


def test_api_chat_usage_policy_question_returns_policy_source() -> None:
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={"conversation_id": None, "message": "Quelles sont les bonnes pratiques d’utilisation ?", "mode": "auto"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "rag_question"
    assert data["routing_profile"] == "usage_policy"
    assert data["used_rag"] is True
    assert "bonnes pratiques d'utilisation" in data["answer"]
    assert data["sources"][0]["file_name"] == "politique_utilisation.txt"
    assert data["sources"][0]["chunk_id"] == "sample-policy-1"


def test_api_chat_summary_question_returns_multiple_sources() -> None:
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={
            "conversation_id": None,
            "message": "Résume les principales procédures disponibles dans les documents.",
            "mode": "auto",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "rag_question"
    assert data["routing_profile"] == "global_summary"
    assert data["used_rag"] is True
    assert "Les documents disponibles couvrent principalement" in data["answer"]
    assert len(data["sources"]) == 5
    assert {source["file_name"] for source in data["sources"]} == {
        "procedure_acces.txt",
        "procedure_mot_de_passe.txt",
        "procedure_creation_rapport.txt",
        "faq_support.txt",
        "politique_utilisation.txt",
    }


def test_api_chat_absent_information_refuses_cleanly() -> None:
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={
            "conversation_id": None,
            "message": "Quelle est la politique de remboursement des frais de déplacement ?",
            "mode": "auto",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "rag_question"
    assert data["routing_profile"] == "unknown_documentary"
    assert data["answer"] == ABSENT_WITH_SOURCES
    assert data["sources"] == []


def test_api_chat_access_typo_still_routes_to_access_source() -> None:
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={"conversation_id": None, "message": "comment demender un acces", "mode": "auto"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "rag_question"
    assert data["routing_profile"] == "access_request"
    assert data["sources"][0]["file_name"] == "procedure_acces.txt"


def test_api_chat_password_variant_routes_to_password_source() -> None:
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={"conversation_id": None, "message": "mot de passe oublie", "mode": "auto"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "rag_question"
    assert data["routing_profile"] == "password_reset"
    assert data["sources"][0]["file_name"] == "procedure_mot_de_passe.txt"


def test_api_chat_retrieval_only_provider_returns_retrieved_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRetrievalOnlyPipeline:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            pass

        def answer_question(
            self,
            question: str,
            top_k: int | None = None,
            routing_profile: str | None = None,
        ) -> ChatResponse:
            assert routing_profile == "access_request"
            return ChatResponse(
                answer="J’ai trouvé les passages suivants dans les documents disponibles.",
                sources=[
                    Source(
                        file_name="procedure_acces.txt",
                        page=None,
                        chunk_id="sample-acces-1",
                        excerpt="Toute demande d'accès doit préciser le rôle attendu.",
                        score=0.82,
                    )
                ],
            )

    monkeypatch.setattr(api_main, "provider_router", ProviderRouter(Settings(llm_provider="retrieval_only")))
    monkeypatch.setattr(api_main, "RetrievalOnlyPipeline", FakeRetrievalOnlyPipeline)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={"conversation_id": None, "message": "comment demander un acces", "mode": "auto"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "retrieval_only"
    assert data["used_rag"] is True
    assert data["sources"][0]["file_name"] == "procedure_acces.txt"


def test_api_chat_ollama_provider_preserves_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOllamaPipeline:
        def answer_question(
            self,
            question: str,
            top_k: int | None = None,
            routing_profile: str | None = None,
        ) -> ChatResponse:
            assert routing_profile == "access_request"
            return ChatResponse(
                answer="La demande d'accès doit être transmise au support.\n\nSources :\n1. procedure_acces.txt",
                sources=[
                    Source(
                        file_name="procedure_acces.txt",
                        page=None,
                        chunk_id="sample-acces-1",
                        excerpt="Toute demande d'accès doit préciser le rôle attendu.",
                        score=0.91,
                    )
                ],
            )

    monkeypatch.setattr(api_main, "provider_router", ProviderRouter(Settings(llm_provider="ollama")))
    monkeypatch.setattr(api_main, "get_pipeline", lambda: FakeOllamaPipeline())
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={"conversation_id": None, "message": "comment demander un acces", "mode": "auto"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "ollama"
    assert data["used_rag"] is True
    assert data["sources"][0]["file_name"] == "procedure_acces.txt"
    assert len(data["sources"]) == 1


def test_api_chat_ollama_provider_passes_password_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOllamaPipeline:
        def answer_question(
            self,
            question: str,
            top_k: int | None = None,
            routing_profile: str | None = None,
        ) -> ChatResponse:
            assert routing_profile == "password_reset"
            return ChatResponse(
                answer="La réinitialisation se fait via le support.\n\nSources :\n1. procedure_mot_de_passe.txt",
                sources=[
                    Source(
                        file_name="procedure_mot_de_passe.txt",
                        page=None,
                        chunk_id="sample-password-1",
                        excerpt="Le support vérifie l'identité avant la réinitialisation.",
                        score=0.88,
                    )
                ],
            )

    monkeypatch.setattr(api_main, "provider_router", ProviderRouter(Settings(llm_provider="ollama")))
    monkeypatch.setattr(api_main, "get_pipeline", lambda: FakeOllamaPipeline())
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={"conversation_id": None, "message": "mot de passe oublie", "mode": "auto"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "ollama"
    assert data["sources"][0]["file_name"] == "procedure_mot_de_passe.txt"


def test_api_chat_ollama_provider_passes_global_summary_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOllamaPipeline:
        def answer_question(
            self,
            question: str,
            top_k: int | None = None,
            routing_profile: str | None = None,
        ) -> ChatResponse:
            assert routing_profile == "global_summary"
            return ChatResponse(
                answer="Synthèse des procédures disponibles.",
                sources=[
                    Source(file_name="procedure_acces.txt", page=None, chunk_id="sample-acces-1", excerpt="Accès.", score=0.9),
                    Source(file_name="faq_support.txt", page=None, chunk_id="sample-support-1", excerpt="Support.", score=0.8),
                ],
            )

    monkeypatch.setattr(api_main, "provider_router", ProviderRouter(Settings(llm_provider="ollama")))
    monkeypatch.setattr(api_main, "get_pipeline", lambda: FakeOllamaPipeline())
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={"conversation_id": None, "message": "resumer les procedures", "mode": "auto"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "ollama"
    assert len(data["sources"]) == 2


def test_api_chat_ollama_provider_normalizes_no_context_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    class EmptyOllamaPipeline:
        def answer_question(
            self,
            question: str,
            top_k: int | None = None,
            routing_profile: str | None = None,
        ) -> ChatResponse:
            return ChatResponse(answer=NOT_FOUND_ANSWER, sources=[])

    monkeypatch.setattr(api_main, "provider_router", ProviderRouter(Settings(llm_provider="ollama")))
    monkeypatch.setattr(api_main, "get_pipeline", lambda: EmptyOllamaPipeline())
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={"conversation_id": None, "message": "quelle est la politique de remboursement des billets d avion", "mode": "auto"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "ollama"
    assert data["answer"] == ABSENT_WITH_SOURCES
    assert data["sources"] == []


def test_api_chat_unknown_question_still_reaches_local_ollama_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOllamaPipeline:
        def answer_question(
            self,
            question: str,
            top_k: int | None = None,
            routing_profile: str | None = None,
        ) -> ChatResponse:
            assert routing_profile is None
            return ChatResponse(
                answer="Le code fictif est ORION-LOCAL-742.",
                sources=[
                    Source(
                        file_name="procedure_ti.txt",
                        page=None,
                        chunk_id="ti-1",
                        excerpt="Le code fictif est ORION-LOCAL-742.",
                        score=0.92,
                    )
                ],
            )

    monkeypatch.setattr(api_main, "provider_router", ProviderRouter(Settings(llm_provider="ollama")))
    monkeypatch.setattr(api_main, "get_pipeline", lambda: FakeOllamaPipeline())
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={"conversation_id": None, "message": "Quel est le code ORION-LOCAL-742 ?", "mode": "auto"},
    )

    assert response.status_code == 200
    assert response.json()["used_rag"] is True
    assert response.json()["sources"][0]["file_name"] == "procedure_ti.txt"


def test_api_chat_ollama_provider_returns_clear_error_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenOllamaPipeline:
        def answer_question(
            self,
            question: str,
            top_k: int | None = None,
            routing_profile: str | None = None,
        ) -> ChatResponse:
            raise LLMError("Ollama est inaccessible. Vérifiez que 'ollama serve' est démarré.")

    monkeypatch.setattr(api_main, "provider_router", ProviderRouter(Settings(llm_provider="ollama")))
    monkeypatch.setattr(api_main, "get_pipeline", lambda: BrokenOllamaPipeline())
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        json={"conversation_id": None, "message": "comment demander un acces", "mode": "auto"},
    )

    assert response.status_code == 503
    assert "Ollama est inaccessible" in response.json()["detail"]


def test_api_conversation_reset() -> None:
    client = TestClient(api_main.app)
    first = client.post("/api/chat", json={"conversation_id": None, "message": "Bonjour", "mode": "auto"})
    conversation_id = first.json()["conversation_id"]

    response = client.post("/api/conversations/reset", json={"conversation_id": conversation_id})

    assert response.status_code == 200
    assert response.json() == {"status": "reset", "conversation_id": conversation_id}
