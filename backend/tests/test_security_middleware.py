import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import main
from app.cli import migrate
from app.config import Settings
from app.database import create_db_engine


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path / 'middleware.sqlite3'}", ai_mode="demo"
    )
    engine = create_db_engine(settings)
    migrate(engine)
    engine.dispose()
    with TestClient(main.create_app(settings), base_url="http://localhost:8001") as test_client:
        yield test_client


def test_untrusted_origin_cannot_trigger_ai_request(client):
    payload = json.dumps({"draft_text": "Нужен журнал посещаемости", "topic": "образование"})
    with patch.object(main, "analyze_task") as operation:
        response = client.post(
            "/api/tasks/analyze",
            content=payload,
            headers={"Origin": "https://untrusted.example", "Content-Type": "text/plain"},
        )
    assert response.status_code == 403
    operation.assert_not_called()


def test_json_api_rejects_simple_content_type_before_ai_call(client):
    payload = json.dumps({"draft_text": "Нужен журнал посещаемости", "topic": "образование"})
    with patch.object(main, "analyze_task") as operation:
        response = client.post(
            "/api/tasks/analyze",
            content=payload,
            headers={"Origin": "http://localhost:8001", "Content-Type": "text/plain"},
        )
    assert response.status_code == 415
    operation.assert_not_called()


def test_same_origin_json_and_configured_frontend_origin_are_allowed(client):
    same_origin = client.post(
        "/api/teams", json={"name": "Origin check"}, headers={"Origin": "http://localhost:8001"}
    )
    assert same_origin.json().get("detail") != "Origin is not allowed"
    assert same_origin.status_code != 415

    configured_origin = client.post(
        "/api/teams", json={"name": "Origin check"}, headers={"Origin": "http://127.0.0.1:8080"}
    )
    assert configured_origin.json().get("detail") != "Origin is not allowed"
    assert configured_origin.headers["access-control-allow-origin"] == "http://127.0.0.1:8080"

    preflight = client.options(
        "/api/teams",
        headers={
            "Origin": "http://127.0.0.1:8080",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:8080"


def test_logout_without_body_keeps_origin_check(client):
    same_origin = client.post("/api/auth/logout", headers={"Origin": "http://localhost:8001"})
    assert same_origin.status_code == 204

    foreign_origin = client.post(
        "/api/auth/logout", headers={"Origin": "https://untrusted.example"}
    )
    assert foreign_origin.status_code == 403


@pytest.mark.parametrize("path", ["/", "/api/health", "/missing"])
def test_security_headers_cover_page_api_and_error_responses(client, path):
    response = client.get(path)
    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_security_headers_cover_rejected_requests_and_cors_preflight(client):
    rejected = client.post(
        "/api/teams",
        json={"name": "Rejected"},
        headers={"Origin": "https://untrusted.example"},
    )
    preflight = client.options(
        "/api/teams",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"},
    )
    assert rejected.status_code == 403
    assert preflight.status_code == 400
    for response in (rejected, preflight):
        assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["x-content-type-options"] == "nosniff"
