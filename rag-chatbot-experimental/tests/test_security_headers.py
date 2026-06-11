import json

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from app.config import Settings


def test_security_headers_are_present() -> None:
    client = TestClient(api_main.app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors" in response.headers["content-security-policy"]


def test_cors_allows_local_frontend_origin_in_development() -> None:
    client = TestClient(api_main.app)

    response = client.options(
        "/api/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_allows_loopback_frontend_origin_in_development() -> None:
    client = TestClient(api_main.app)

    response = client.options(
        "/api/chat",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_cors_does_not_allow_unknown_origin() -> None:
    client = TestClient(api_main.app)

    response = client.options(
        "/api/chat",
        headers={
            "Origin": "http://site-non-autorise.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_health_response_does_not_expose_secret_fields() -> None:
    client = TestClient(api_main.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "rag-api"}
    serialized = json.dumps(response.json()).lower()
    assert "openrouter_api_key" not in serialized
    assert "api_key" not in serialized
    assert "token" not in serialized
    assert ".env" not in serialized


def test_production_cors_rejects_wildcard_origin() -> None:
    settings = Settings(environment="production", allowed_origins_production=("*",))

    with pytest.raises(ValueError, match="ne doit pas contenir"):
        settings.validate()
