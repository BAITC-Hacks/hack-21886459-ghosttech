from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import create_app
from app.cli import migrate
from app.config import Settings
from app.database import create_db_engine
from app.models import Participant, Progress, Proposal, Task, Team

NOW = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
START = NOW.replace(day=1, hour=0)
OLD = datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc)
FUTURE = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("app.leaderboard.utcnow", lambda: NOW)
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path / 'rank.db'}", ai_mode="demo"
    )
    engine = create_db_engine(settings)
    migrate(engine)
    with Session(engine) as db, db.begin():
        db.add_all(
            [
                Participant(id="a", name="Business A", role="business"),
                Participant(id="b", name="Business B", role="business"),
                Participant(id="student", name="Student", role="student"),
                Team(id="x", name="Team X", base_points=200, contact="hello@example.com"),
                Team(id="y", name="Team Y"),
            ]
        )
        db.flush()
        for id_, owner, score, created, confirmed in [
            ("a1", "a", 60, START, True),
            ("a2", "a", 80, NOW, True),
            ("old", "b", 100, OLD, True),
            ("draft", "a", 100, NOW, False),
            ("future", "b", 100, FUTURE, True),
        ]:
            db.add(
                Task(
                    id=id_,
                    owner_id=owner,
                    title=id_,
                    topic="education",
                    confirmed=confirmed,
                    score=score,
                    level="ready",
                    created_at=created,
                    contact=f"{id_}@example.com",
                )
            )
        db.flush()
        for id_, task, team, status in [
            ("p1", "a1", "x", "accepted"),
            ("p2", "old", "y", "accepted"),
            ("hidden", "draft", "y", "accepted"),
            ("pending", "a2", "x", "pending"),
        ]:
            db.add(
                Proposal(
                    id=id_,
                    task_id=task,
                    team_id=team,
                    idea="Idea",
                    plan="Plan",
                    deadline=date(2026, 12, 1),
                    status=status,
                )
            )
        db.flush()
        for proposal, stage, points, created in [
            ("p1", "prototype", 10, OLD),
            ("p1", "final", 30, NOW),
            ("p2", "testing", 20, START),
            ("p2", "final", 30, NOW),
            ("hidden", "final", 30, NOW),
            ("pending", "prototype", 10, NOW),
            ("p2", "prototype", 10, FUTURE),
        ]:
            db.add(Progress(proposal_id=proposal, stage=stage, points=points, created_at=created))
    engine.dispose()
    with TestClient(create_app(settings)) as client:
        yield client


def test_month_uses_event_dates_and_excludes_undated_base_hidden_and_future(client):
    response = client.get("/api/leaderboard")
    assert response.status_code == 200, response.text
    board = response.json()
    assert board["starts_at"] == "2026-09-01T00:00:00Z"
    assert [row["profile"]["id"] for row in board["businesses"]] == ["a", "b"]
    a, b = board["businesses"]
    assert (a["points"], a["published_tasks"], a["average_readiness"]) == (170, 2, 70)
    assert (b["points"], b["published_tasks"], b["completed_tasks"]) == (50, 0, 1)
    assert [
        (row["team"]["id"], row["points"], row["completed_tasks"]) for row in board["teams"]
    ] == [("y", 50, 1), ("x", 30, 1)]
    assert [row["rank"] for row in board["teams"]] == [1, 2]


def test_all_time_includes_historical_points_once_and_base(client):
    board = client.get("/api/leaderboard?period=all").json()
    assert board["starts_at"] is None
    assert [(r["profile"]["id"], r["points"]) for r in board["businesses"]] == [
        ("a", 180),
        ("b", 150),
    ]
    assert [(r["team"]["id"], r["points"]) for r in board["teams"]] == [("x", 240), ("y", 50)]
    assert board["teams"][0]["confirmed_stages"] == 2


def test_limits_empty_and_stable_ties(client):
    assert len(client.get("/api/leaderboard?limit=1").json()["teams"]) == 1
    for query in ("period=week", "limit=0", "limit=51"):
        assert client.get("/api/leaderboard?" + query).status_code == 422
    with Session(client.app.state.engine) as db, db.begin():
        for stage in db.query(Progress).all():
            stage.created_at = OLD
        for task in db.query(Task).all():
            task.created_at = OLD
    board = client.get("/api/leaderboard").json()
    assert board["businesses"] == board["teams"] == []


def test_business_profile_only_published_tasks_and_contacts(client):
    result = client.get("/api/profiles/businesses/a?limit=1").json()
    assert result["total_tasks"] == 2 and result["open_tasks"] == 1
    assert result["tasks"][0]["id"] == "a2" and result["tasks"][0]["open_for_proposals"]
    assert result["contacts"] == ["a1@example.com", "a2@example.com"]
    page = client.get("/api/profiles/businesses/a?limit=1&offset=1").json()
    assert page["tasks"][0]["id"] == "a1" and not page["tasks"][0]["open_for_proposals"]
    assert client.get("/api/profiles/businesses/student").status_code == 404
    assert client.get("/api/profiles/businesses/missing").status_code == 404


def test_team_profile_shows_only_accepted_public_projects(client):
    result = client.get("/api/profiles/teams/y").json()
    assert result["total_projects"] == 1
    assert result["projects"][0]["task"]["id"] == "old"
    assert client.get("/api/profiles/teams/missing").status_code == 404
    assert client.get("/api/profiles/teams/x?limit=0").status_code == 422
    x = client.get("/api/profiles/teams/x").json()
    assert x["team"]["contact"] == "hello@example.com"
    assert x["total_projects"] == 1


def test_contact_is_optional_and_older_clients_do_not_erase_it(client):
    account = client.post(
        "/api/auth/register",
        json={
            "email": "contact-student@example.test",
            "password": "correct-horse-battery",
            "name": "Contact student",
            "role": "student",
        },
    )
    assert account.status_code == 201, account.text
    response = client.post(
        "/api/teams", json={"name": "Contact team", "contact": "  team@example.com  "}
    )
    assert response.status_code == 201
    team = response.json()
    assert team["contact"] == "team@example.com"
    edited = client.patch("/api/teams/" + team["id"], json={"name": "Renamed"}).json()
    assert edited["contact"] == "team@example.com"
    edited = client.patch(
        "/api/teams/" + team["id"], json={"name": "Renamed", "contact": ""}
    ).json()
    assert edited["contact"] == ""
    assert (
        client.post("/api/teams", json={"name": "Too long", "contact": "x" * 501}).status_code
        == 422
    )


def test_equal_points_have_stable_rank(client):
    with Session(client.app.state.engine) as db, db.begin():
        db.add(Progress(proposal_id="p1", stage="testing", points=20, created_at=NOW))
    first = client.get("/api/leaderboard").json()["teams"]
    second = client.get("/api/leaderboard").json()["teams"]
    assert [(row["team"]["id"], row["points"]) for row in first] == [("x", 50), ("y", 50)]
    assert first == second


def test_new_calendar_month_resets_activity_without_resetting_history(client, monkeypatch):
    monkeypatch.setattr("app.leaderboard.utcnow", lambda: FUTURE)
    board = client.get("/api/leaderboard").json()
    assert board["starts_at"] == "2026-10-01T00:00:00Z"
    assert [(row["profile"]["id"], row["points"]) for row in board["businesses"]] == [("b", 110)]
    assert [(row["team"]["id"], row["points"]) for row in board["teams"]] == [("y", 10)]
