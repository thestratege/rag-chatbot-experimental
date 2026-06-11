import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import main as api_main
from app import auth as auth_module
from app.auth import (
    ANONYMOUS_DEMO_USER_ID,
    DEMO_ADMIN_ID,
    DEMO_USER_ID,
    UserContext,
    ensure_required_groups,
    resolve_current_user,
)
from app.config import Settings
from app.conversation_manager import ConversationManager
from app.provider_router import ProviderRouter
from app.schemas import ChatResponse, IngestionResult


def mock_auth_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "demo",
        "auth_enabled": True,
        "auth_provider": "mock",
        "demo_auth_token": "test-user-token",
        "demo_admin_auth_token": "test-admin-token",
        "llm_provider": "mock",
    }
    values.update(overrides)
    return Settings(**values)


def test_auth_disabled_returns_anonymous_demo_user() -> None:
    user = resolve_current_user(Settings(auth_enabled=False), authorization=None)

    assert user.user_id == ANONYMOUS_DEMO_USER_ID
    assert user.auth_enabled is False
    assert user.is_authenticated is False
    assert user.token_present is False


def test_auth_enabled_without_token_raises_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_current_user(Settings(auth_enabled=True, auth_provider="entra"), authorization=None)

    assert exc_info.value.status_code == 401
    assert "Authentification requise" in str(exc_info.value.detail)


def test_mock_auth_accepts_configured_demo_token() -> None:
    user = resolve_current_user(
        mock_auth_settings(),
        authorization="Bearer test-user-token",
    )

    assert user.user_id == DEMO_USER_ID
    assert user.auth_provider == "mock"
    assert user.is_authenticated is True
    assert user.roles == ("demo",)
    assert user.token_present is True


def test_mock_auth_accepts_configured_admin_token() -> None:
    user = resolve_current_user(
        mock_auth_settings(),
        authorization="Bearer test-admin-token",
    )

    assert user.user_id == DEMO_ADMIN_ID
    assert user.auth_provider == "mock"
    assert user.is_authenticated is True
    assert user.roles == ("admin",)
    assert user.token_present is True


def test_mock_auth_rejects_invalid_demo_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_current_user(
            mock_auth_settings(),
            authorization="Bearer mauvais-token",
        )

    assert exc_info.value.status_code == 401
    assert "invalide" in str(exc_info.value.detail)


def test_auth_rejects_unsupported_provider_with_clear_500() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_current_user(
            Settings(auth_enabled=True, auth_provider="unsupported"),
            authorization="Bearer token",
        )

    assert exc_info.value.status_code == 500
    assert "non supporté" in str(exc_info.value.detail)


def test_required_groups_raise_403_when_user_is_not_authorized() -> None:
    user = UserContext(
        user_id="user@example.org",
        auth_provider="entra",
        is_authenticated=True,
        auth_enabled=True,
        groups=("group-a",),
    )

    with pytest.raises(HTTPException) as exc_info:
        ensure_required_groups(user, ("group-b",))

    assert exc_info.value.status_code == 403


def test_api_chat_still_works_when_auth_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(auth_enabled=False, llm_provider="mock")
    monkeypatch.setattr(auth_module, "settings", settings)
    monkeypatch.setattr(api_main, "provider_router", ProviderRouter(settings))
    monkeypatch.setattr(api_main, "conversation_manager", ConversationManager(history_limit=10))
    client = TestClient(api_main.app)

    response = client.post("/api/chat", json={"conversation_id": None, "message": "Bonjour", "mode": "auto"})

    assert response.status_code == 200
    assert response.json()["provider"] == "mock"


def test_api_chat_requires_token_when_mock_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = mock_auth_settings()
    monkeypatch.setattr(auth_module, "settings", settings)
    client = TestClient(api_main.app)

    response = client.post("/api/chat", json={"conversation_id": None, "message": "Bonjour", "mode": "auto"})

    assert response.status_code == 401
    assert "Authentification requise" in response.json()["detail"]


def test_api_chat_unauthorized_response_keeps_cors_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = mock_auth_settings()
    monkeypatch.setattr(auth_module, "settings", settings)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        headers={"Origin": "http://localhost:5173"},
        json={"conversation_id": None, "message": "Bonjour", "mode": "auto"},
    )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_api_chat_rejects_invalid_mock_token(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = mock_auth_settings()
    monkeypatch.setattr(auth_module, "settings", settings)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        headers={"Authorization": "Bearer mauvais-token"},
        json={"conversation_id": None, "message": "Bonjour", "mode": "auto"},
    )

    assert response.status_code == 401
    assert "invalide" in response.json()["detail"]


def test_api_chat_accepts_valid_mock_token(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = mock_auth_settings()
    monkeypatch.setattr(auth_module, "settings", settings)
    monkeypatch.setattr(api_main, "provider_router", ProviderRouter(settings))
    monkeypatch.setattr(api_main, "conversation_manager", ConversationManager(history_limit=10))
    client = TestClient(api_main.app)

    response = client.post(
        "/api/chat",
        headers={"Authorization": "Bearer test-user-token"},
        json={"conversation_id": None, "message": "Bonjour", "mode": "auto"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "mock"
    assert "test-user-token" not in response.text


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer mauvais-token"},
    ],
)
def test_legacy_chat_rejects_missing_or_invalid_mock_token(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
) -> None:
    settings = mock_auth_settings()
    monkeypatch.setattr(auth_module, "settings", settings)
    client = TestClient(api_main.app)

    response = client.post("/chat", headers=headers, json={"question": "Comment réinitialiser mon mot de passe ?"})

    assert response.status_code == 401


def test_legacy_chat_accepts_valid_mock_token(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePipeline:
        def answer_question(self, question: str, top_k: int | None = None) -> ChatResponse:
            return ChatResponse(answer="Réponse de démonstration.", sources=[])

    settings = mock_auth_settings()
    monkeypatch.setattr(auth_module, "settings", settings)
    monkeypatch.setattr(api_main, "get_pipeline", lambda: FakePipeline())
    client = TestClient(api_main.app)

    response = client.post(
        "/chat",
        headers={"Authorization": "Bearer test-user-token"},
        json={"question": "Comment réinitialiser mon mot de passe ?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Réponse de démonstration."


def test_demo_environment_accepts_mock_auth_configuration() -> None:
    settings = Settings(
        environment="demo",
        auth_enabled=True,
        auth_provider="mock",
        demo_auth_token="test-user-token",
        demo_admin_auth_token="test-admin-token",
    )

    settings.validate()


def test_mock_auth_requires_explicit_demo_token() -> None:
    settings = Settings(
        environment="demo",
        auth_enabled=True,
        auth_provider="mock",
        demo_auth_token="",
        demo_admin_auth_token="test-admin-token",
    )

    with pytest.raises(ValueError, match="DEMO_AUTH_TOKEN"):
        settings.validate()


def test_mock_auth_is_rejected_in_production() -> None:
    settings = Settings(
        environment="production",
        auth_enabled=True,
        auth_provider="mock",
        demo_auth_token="test-user-token",
        demo_admin_auth_token="test-admin-token",
    )

    with pytest.raises(ValueError, match="hors production"):
        settings.validate()


def test_health_stays_public_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module,
        "settings",
        mock_auth_settings(),
    )
    client = TestClient(api_main.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "rag-api"}


def test_root_is_protected_by_default_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "settings", mock_auth_settings())
    client = TestClient(api_main.app)

    response = client.get("/")

    assert response.status_code == 401


def test_unknown_route_is_denied_before_routing_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "settings", mock_auth_settings())
    client = TestClient(api_main.app)

    response = client.get("/future-sensitive-route")

    assert response.status_code == 401


def test_swagger_remains_explicitly_public_in_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "settings", mock_auth_settings())
    client = TestClient(api_main.app)

    response = client.get("/docs")

    assert response.status_code == 200


def test_reset_conversation_requires_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "settings", mock_auth_settings())
    client = TestClient(api_main.app)

    response = client.post("/api/conversations/reset", json={"conversation_id": "demo-conversation"})

    assert response.status_code == 401


def test_ingest_requires_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "settings", mock_auth_settings())
    client = TestClient(api_main.app)

    response = client.post("/ingest")

    assert response.status_code == 401


def test_ingest_rejects_demo_user_without_admin_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "settings", mock_auth_settings())
    client = TestClient(api_main.app)

    response = client.post("/ingest", headers={"Authorization": "Bearer test-user-token"})

    assert response.status_code == 403
    assert "admin" in response.json()["detail"]


def test_ingest_forbidden_response_keeps_cors_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "settings", mock_auth_settings())
    client = TestClient(api_main.app)

    response = client.post(
        "/ingest",
        headers={
            "Origin": "http://localhost:5173",
            "Authorization": "Bearer test-user-token",
        },
    )

    assert response.status_code == 403
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "test-user-token" not in response.text


def test_ingest_accepts_demo_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePipeline:
        def ingest_documents(self) -> IngestionResult:
            return IngestionResult(documents_loaded=2, chunks_created=3, chunks_indexed=3)

    monkeypatch.setattr(auth_module, "settings", mock_auth_settings())
    monkeypatch.setattr(api_main, "get_pipeline", lambda: FakePipeline())
    client = TestClient(api_main.app)

    response = client.post("/ingest", headers={"Authorization": "Bearer test-admin-token"})

    assert response.status_code == 200
    assert response.json()["chunks_indexed"] == 3
    assert "test-admin-token" not in response.text
