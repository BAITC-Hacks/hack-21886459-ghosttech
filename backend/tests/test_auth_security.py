"""Integration checks for real identities, ownership, and assistant cost limits."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.cli import migrate
from app.config import Settings
from app.database import create_db_engine
from app.main import create_app


@pytest.fixture
def site(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'auth.sqlite3'}",
        ai_mode="demo",
        ai_daily_limit=2,
    )
    engine = create_db_engine(settings)
    migrate(engine)
    engine.dispose()
    app = create_app(settings)
    with TestClient(app) as guest:
        clients = [guest]

        def account(email: str, role: str):
            client = TestClient(app)
            clients.append(client)
            response = client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "password": "CorrectHorseBattery1!",
                    "name": email.split("@")[0],
                    "role": role,
                },
            )
            assert response.status_code == 201, response.text
            assert "HttpOnly" in response.headers["set-cookie"]
            return client, response.json()

        yield guest, account
        for client in clients[1:]:
            client.close()


def test_anonymous_access_owner_checks_and_demo_read_only(site):
    guest, account = site
    owner, owner_info = account("owner@example.test", "business")
    other_business, other_info = account("other@example.test", "business")
    student, student_info = account("student@example.test", "student")
    other_student, _ = account("another@example.test", "student")

    assert guest.post("/api/tasks", json={"card": {}}).status_code == 401
    assert guest.post("/api/teams", json={"name": "No"}).status_code == 401
    assert student.post("/api/tasks", json={"card": {}}).status_code == 403
    assert owner.post("/api/teams", json={"name": "No"}).status_code == 403

    card = {"title": "Private business task", "topic": "образование"}
    assert (
        owner.post("/api/tasks", json={"card": card, "owner_id": other_info["id"]}).status_code
        == 403
    )
    response = owner.post("/api/tasks", json={"card": card, "confirmed": False})
    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft["owner"]["id"] == owner_info["id"]
    path = f"/api/tasks/{draft['id']}"
    assert guest.get(path).status_code == 404
    assert other_business.get(path).status_code == 404
    assert all(
        row["id"] != draft["id"]
        for row in guest.get("/api/tasks", params={"include_drafts": True}).json()
    )
    assert any(
        row["id"] == draft["id"]
        for row in owner.get("/api/tasks", params={"include_drafts": True}).json()
    )
    assert other_business.patch(path, json={"confirmed": True}).status_code in {403, 404}
    assert owner.patch(path, json={"confirmed": True}).status_code == 200

    first_team = student.post("/api/teams", json={"name": "Students"})
    second_team = other_student.post("/api/teams", json={"name": "Others"})
    assert first_team.status_code == second_team.status_code == 201
    team_id = first_team.json()["id"]
    other_team_id = second_team.json()["id"]
    assert student.get("/api/auth/me").json()["team_id"] == team_id
    assert other_student.patch(f"/api/teams/{team_id}", json={"name": "Hijacked"}).status_code in {
        403,
        404,
    }
    assert student.patch(f"/api/teams/{team_id}", json={"name": "Updated"}).status_code == 200

    proposal = {
        "team_id": team_id,
        "idea": "A useful prototype",
        "plan": "Build and test it",
        "deadline": str(date.today() + timedelta(days=7)),
    }
    proposals_path = f"{path}/proposals"
    assert (
        student.post(proposals_path, json=proposal | {"team_id": other_team_id}).status_code == 403
    )
    assert guest.post(proposals_path, json=proposal).status_code == 401
    response = student.post(proposals_path, json=proposal)
    assert response.status_code == 201, response.text
    proposal_id = response.json()["id"]
    decision = f"/api/proposals/{proposal_id}/decision"
    progress = f"/api/proposals/{proposal_id}/progress"
    assert other_business.patch(decision, json={"decision": "accepted"}).status_code in {
        403,
        404,
    }
    assert guest.patch(decision, json={"decision": "accepted"}).status_code == 401
    assert owner.patch(decision, json={"decision": "accepted"}).status_code == 200
    assert student.post(progress, json={"stage": "prototype"}).status_code == 403
    assert guest.post(progress, json={"stage": "prototype"}).status_code == 401
    assert owner.post(progress, json={"stage": "prototype"}).status_code == 201

    assert guest.get(proposals_path).json() == []
    assert student_info["team_id"] is None


def test_session_revocation_and_assistant_quota(site):
    guest, account = site
    business, identity = account("quota@example.test", "business")
    body = {"draft_text": "Нужен журнал посещаемости для учебного центра", "topic": "образование"}

    with patch("app.main.analyze_task") as operation:
        assert guest.post("/api/tasks/analyze", json=body).status_code == 401
        operation.assert_not_called()

    assert business.get("/api/auth/me").json()["id"] == identity["id"]
    assert business.post("/api/tasks/analyze", json=body).status_code == 200
    assert business.post("/api/tasks/build-card", json=body).status_code == 200
    assert business.post("/api/tasks/analyze", json=body).status_code == 429

    assert business.post("/api/auth/logout").status_code == 204
    assert business.get("/api/auth/me").status_code == 401
    assert business.post("/api/tasks/analyze", json=body).status_code == 401
