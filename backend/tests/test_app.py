from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.api import create_app
from app.cli import migrate
from app.config import BACKEND_DIR, Settings
from app.database import create_db_engine
from app.models import Progress, Proposal, Task, Team
from app.schemas import Card
from app.scoring import score_card
from app.seed import seed_database


@pytest.fixture
def settings(tmp_path):
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}", ai_mode="demo"
    )
    engine = create_db_engine(settings)
    migrate(engine)
    engine.dispose()
    return settings


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        register(client, "business@example.test", "business")
        yield client


@pytest.fixture
def student_client(client):
    with TestClient(client.app) as student:
        register(student, "student@example.test", "student")
        yield student


@pytest.fixture
def second_student_client(client):
    with TestClient(client.app) as student:
        register(student, "second-student@example.test", "student")
        yield student


def register(client, email, role):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct-horse-battery", "name": email, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def task(client, confirmed=True, **fields):
    response = client.post(
        "/api/tasks",
        json={
            "card": {"title": "Test task", "topic": "образование", **fields},
            "confirmed": confirmed,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def team(client, name="Team"):
    response = client.post("/api/teams", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def proposal_payload(team_id):
    return {
        "team_id": team_id,
        "idea": "Test idea",
        "plan": "First build, then test",
        "deadline": "2027-01-10",
        "prototype_url": "https://example.com/prototype",
    }


def test_catalog_filters_publication_and_update(client):
    low = task(client)
    high = task(
        client, topic="ритейл", context="Подробное описание проблемы бизнеса и текущих процессов."
    )
    draft = task(client, confirmed=False)
    assert [item["id"] for item in client.get("/api/tasks").json()] == [high["id"], low["id"]]
    assert client.get("/api/tasks?topic=ритейл").json()[0]["id"] == high["id"]
    assert len(client.get("/api/tasks?limit=1&offset=1").json()) == 1
    assert len(client.get("/api/tasks?include_drafts=true").json()) == 3
    assert client.get("/api/tasks?limit=999").status_code == 422
    assert client.get("/api/tasks?level=unknown").status_code == 422
    assert client.get("/api/tasks/missing").status_code == 404
    assert client.post("/api/tasks", json={"card": {}, "confirmed": True}).status_code == 422
    assert client.post("/api/tasks", json={"card": {}, "score": 100}).status_code == 422
    assert client.patch(f"/api/tasks/{draft['id']}", json={"confirmed": True}).status_code == 200
    result = client.patch(
        f"/api/tasks/{low['id']}",
        json={
            "card": {"title": "Updated", "topic": "ритейл", "need": "x" * 40},
            "confirmed": True,
        },
    ).json()
    assert result["score"] == 10 and result["card"]["title"] == "Updated"
    assert "owner_id" not in result
    result = client.patch(f"/api/tasks/{low['id']}", json={"card": {"title": "Changed"}}).json()
    assert result["confirmed"] is False and result["score"] == 0
    assert client.patch(f"/api/tasks/{low['id']}", json={"confirmed": True}).status_code == 422
    assert client.patch(f"/api/tasks/{low['id']}", json={}).status_code == 422


def test_proposals_decisions_and_points(client, student_client):
    business_task, working_team = task(client), team(student_client)
    url = f"/api/tasks/{business_task['id']}/proposals"
    payload = proposal_payload(working_team["id"])
    assert student_client.post(url, json=payload | {"team_id": "missing"}).status_code == 403
    assert (
        student_client.post(
            url, json=payload | {"prototype_url": "javascript:alert(1)"}
        ).status_code
        == 422
    )
    response = student_client.post(url, json=payload)
    assert response.status_code == 201, response.text
    proposal = response.json()
    assert student_client.post(url, json=payload).status_code == 409
    assert client.get(url).json()[0]["id"] == proposal["id"]
    assert client.get("/api/tasks").json()[0]["proposals_count"] == 1
    decision = f"/api/proposals/{proposal['id']}/decision"
    progress = f"/api/proposals/{proposal['id']}/progress"
    assert client.post(progress, json={"stage": "prototype"}).status_code == 409
    assert client.patch(decision, json={"decision": "invalid"}).status_code == 422
    assert client.patch(decision, json={"decision": "accepted"}).status_code == 200
    assert client.patch(decision, json={"decision": "rejected"}).status_code == 409
    assert client.post(progress, json={"stage": "unknown"}).status_code == 422
    for stage, total in [("prototype", 10), ("testing", 30), ("final", 60)]:
        response = client.post(progress, json={"stage": stage})
        assert response.status_code == 201, response.text
        assert response.json()["points_total"] == total
        assert response.json()["team_points_total"] == total
        assert client.post(progress, json={"stage": stage}).status_code == 409
    assert client.get("/api/teams").json()[0]["points"] == 60
    with Session(client.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Progress)) == 3


def test_draft_and_rejected_proposals_cannot_progress(client, student_client):
    draft, working_team = task(client, confirmed=False), team(student_client)
    url = f"/api/tasks/{draft['id']}/proposals"
    payload = proposal_payload(working_team["id"])
    assert student_client.post(url, json=payload).status_code == 409
    client.patch(f"/api/tasks/{draft['id']}", json={"confirmed": True})
    proposal = student_client.post(url, json=payload).json()
    client.patch(f"/api/proposals/{proposal['id']}/decision", json={"decision": "rejected"})
    assert (
        client.post(
            f"/api/proposals/{proposal['id']}/progress", json={"stage": "final"}
        ).status_code
        == 409
    )


def test_concurrent_stage_awards_only_once(client, student_client):
    created, working_team = task(client), team(student_client)
    proposal = student_client.post(
        f"/api/tasks/{created['id']}/proposals", json=proposal_payload(working_team["id"])
    ).json()
    client.patch(f"/api/proposals/{proposal['id']}/decision", json={"decision": "accepted"})
    path = f"/api/proposals/{proposal['id']}/progress"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: client.post(path, json={"stage": "prototype"}).status_code, range(2))
        )
    assert sorted(results) == [201, 409]
    assert client.get("/api/teams").json()[0]["points"] == 10


def test_team_management_and_validation(student_client):
    assert student_client.post("/api/teams", json={"name": "X", "points": 100}).status_code == 422
    assert student_client.post("/api/teams", json={"name": "   "}).status_code == 422
    created = team(student_client)
    response = student_client.patch(
        f"/api/teams/{created['id']}", json={"name": "New", "tech": ["Python"]}
    )
    assert response.json()["name"] == "New"
    assert student_client.patch("/api/teams/missing", json={"name": "X"}).status_code == 404


def test_team_proposals_filter_pagination_and_progress(
    client, student_client, second_student_client
):
    first, second = team(student_client, "First"), team(second_student_client, "Second")
    task_a, task_b = task(client), task(client)
    proposal_a = student_client.post(
        f"/api/tasks/{task_a['id']}/proposals", json=proposal_payload(first["id"])
    ).json()
    student_client.post(f"/api/tasks/{task_b['id']}/proposals", json=proposal_payload(first["id"]))
    second_student_client.post(
        f"/api/tasks/{task_a['id']}/proposals", json=proposal_payload(second["id"])
    )
    client.patch(f"/api/proposals/{proposal_a['id']}/decision", json={"decision": "accepted"})
    client.post(f"/api/proposals/{proposal_a['id']}/progress", json={"stage": "prototype"})
    rows = client.get("/api/proposals", params={"team_id": first["id"]}).json()
    assert len(rows) == 2
    assert all(row["team_id"] == first["id"] for row in rows)
    accepted = next(row for row in rows if row["id"] == proposal_a["id"])
    assert accepted["status"] == "accepted" and accepted["stages_done"] == ["prototype"]
    assert (
        client.get(
            "/api/proposals", params={"team_id": first["id"], "offset": 1, "limit": 1}
        ).json()
        == rows[1:]
    )
    assert len(client.get("/api/proposals").json()) == 3
    assert client.get("/api/proposals?team_id=missing").status_code == 404
    assert client.get("/api/proposals?limit=101").status_code == 422


def test_assistant_scoring_and_boundaries(client):
    assert score_card(Card()).score == 0
    full = Card(**{field: "Полное описание " * 4 for field in Card.model_fields})
    full.success_criteria = "Сократить затраты на 30%"
    assert score_card(full).score == 100
    assert score_card(full).level == "priority"
    full.success_criteria = "Улучшить процесс"
    assert score_card(full).score == 95
    assert score_card(full).missing[0].potential_points == 5
    assert score_card(Card(context="x" * 9)).score == 0
    assert score_card(Card(context="x" * 10)).score == 5
    assert score_card(Card(context="x" * 40)).score == 10
    assert client.post("/api/tasks/analyze", json={"draft_text": ""}).status_code == 422
    result = client.post(
        "/api/tasks/analyze", json={"draft_text": "Нужен учёт", "topic": "ритейл"}
    ).json()
    assert 3 <= len(result["questions"]) <= 5 and result["mode"] == "demo"
    built = client.post(
        "/api/tasks/build-card",
        json={
            "draft_text": "Нужен учёт",
            "topic": "ритейл",
            "answers": [{"question_id": "q1", "field": "data", "answer": "Таблицы заказов"}],
        },
    ).json()
    assert built["card"]["data"] == "Таблицы заказов"
    assert built["card"]["users"] == ""
    assert client.post("/api/tasks/score", json={"card": built["card"]}).status_code == 200


def test_auth_cors_static_files_and_health(client):
    assert client.get("/api/health").json()["database"] == "sqlite"
    for asset in ["/", "/app.js", "/api.js", "/styles.css", "/static/styles.css"]:
        assert client.get(asset).status_code == 200
    assert client.get("/.env").status_code == 404
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/login", json={}).status_code == 422
    with TestClient(client.app) as anonymous:
        assert anonymous.get("/api/auth/me").status_code == 401
        assert anonymous.post("/api/tasks", json={"card": {}}).status_code == 401
    schema = client.get("/openapi.json").json()
    assert "/api/auth/register" in schema["paths"]
    assert "/api/auth/me" in schema["paths"]
    response = client.options(
        "/api/tasks",
        headers={
            "Origin": "http://127.0.0.1:8080",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8080"
    assert (
        client.options(
            "/api/tasks",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        ).status_code
        == 400
    )


def test_seed_idempotency_and_restart(settings):
    engine = create_db_engine(settings)
    migrate(engine)
    with Session(engine) as db, db.begin():
        assert seed_database(db) == {
            "tasks": 85,
            "teams": 25,
            "proposals": 207,
            "participants": 100,
            "progress": 104,
        }
        db.get(Task, "t1").title = "Edited title"
    with Session(engine) as db, db.begin():
        assert not any(seed_database(db).values())
        assert db.get(Task, "t1").title == "Edited title"
        assert db.scalar(select(func.count()).select_from(Task)) == 85
        assert db.scalar(select(func.count()).select_from(Team)) == 25
        assert db.scalar(select(func.count()).select_from(Proposal)) == 207
        assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1
    assert "users" not in inspect(engine).get_table_names()
    engine.dispose()
    with TestClient(create_app(settings)) as client:
        assert len(client.get("/api/tasks?limit=100").json()) == 85
        assert client.get("/api/tasks/t1").json()["card"]["title"] == "Edited title"


def test_migration_preserves_legacy_notes(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'legacy.sqlite3'}")
    engine = create_db_engine(settings)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE notes (id INTEGER PRIMARY KEY, text TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO notes VALUES (1, 'Keep me')"))
    migrate(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT text FROM notes")).scalar() == "Keep me"
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.attributes["connection"] = connection
        command.check(config)
    engine.dispose()


@pytest.fixture
def catalog_cases(client):
    from datetime import datetime, timedelta, timezone

    from app.models import Participant

    rows = [
        task(client, title="Анализ продаж", topic="ритейл", context="x" * 40),
        task(client, title="Панель продаж", topic="ритейл", context="x" * 40, need="x" * 40),
        task(client, title="Бот школы", topic="образование"),
        task(client, title="Сводка продаж", topic="ритейл", context="x" * 40),
    ]
    task(client, confirmed=False, title="Скрытый черновик", context="x" * 40)
    with Session(client.app.state.engine) as db, db.begin():
        db.add(Participant(id="catalog-owner", name="Тестовый заказчик", role="business"))
        db.flush()
        for index, row in enumerate(rows):
            record = db.get(Task, row["id"])
            record.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
            record.work_tags = [
                ["аналитика"],
                ["аналитика", "веб-приложение"],
                ["бот"],
                ["аналитика данных"],
            ][index]
            if index in [0, 1]:
                record.owner_id = "catalog-owner"
    for index in range(3):
        with TestClient(client.app) as respondent_client:
            register(respondent_client, f"respondent-{index}@example.test", "student")
            respondent = team(respondent_client, f"Respondent {index}")
            for row_index in range(index, 3):
                assert (
                    respondent_client.post(
                        f"/api/tasks/{rows[row_index]['id']}/proposals",
                        json=proposal_payload(respondent["id"]),
                    ).status_code
                    == 201
                )
    return rows


@pytest.mark.parametrize(
    "sort, expected",
    [
        ("score_desc", [1, 3, 0, 2]),
        ("score_asc", [2, 3, 0, 1]),
        ("newest", [3, 2, 1, 0]),
        ("oldest", [0, 1, 2, 3]),
        ("proposals_desc", [2, 1, 0, 3]),
    ],
)
def test_catalog_sorting_before_pagination(client, catalog_cases, sort, expected):
    expected_ids = [catalog_cases[index]["id"] for index in expected]
    whole = client.get("/api/tasks", params={"sort": sort}).json()
    assert [row["id"] for row in whole] == expected_ids
    paged = []
    for offset in [0, 2]:
        paged.extend(
            client.get("/api/tasks", params={"sort": sort, "offset": offset, "limit": 2}).json()
        )
    assert [row["id"] for row in paged] == expected_ids
    newest_retail = client.get(
        "/api/tasks", params={"topic": "ритейл", "sort": "newest", "limit": 1}
    ).json()
    assert newest_retail[0]["id"] == catalog_cases[3]["id"]


def test_combined_catalog_filters_exact_tags_and_response_counts(client, catalog_cases):
    rows = client.get(
        "/api/tasks",
        params={
            "topic": "ритейл",
            "level": "draft",
            "owner_id": "catalog-owner",
            "search": "ПРОДАЖ",
            "work_type": "аналитика",
            "proposals": "has",
            "sort": "oldest",
        },
    ).json()
    assert [row["id"] for row in rows] == [catalog_cases[0]["id"], catalog_cases[1]["id"]]
    assert [row["proposals_count"] for row in rows] == [1, 2]
    without = client.get("/api/tasks", params={"proposals": "none"}).json()
    assert [row["id"] for row in without] == [catalog_cases[3]["id"]]
    assert (
        client.get("/api/tasks", params={"work_type": "аналитика", "proposals": "none"}).json()
        == []
    )
    assert client.get("/api/tasks", params={"work_type": "анализ"}).json() == []
    assert client.get("/api/tasks?sort=unknown").status_code == 422
    assert client.get("/api/tasks?proposals=unknown").status_code == 422


def test_catalog_sort_ties_are_stable(client, catalog_cases):
    from datetime import datetime, timezone

    with Session(client.app.state.engine) as db, db.begin():
        for row in catalog_cases:
            record = db.get(Task, row["id"])
            record.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            record.score = 10
    expected = sorted(row["id"] for row in catalog_cases)
    for sort in ["score_desc", "score_asc", "newest", "oldest"]:
        page_ids = [
            client.get("/api/tasks", params={"sort": sort, "offset": i, "limit": 1}).json()[0]["id"]
            for i in range(4)
        ]
        assert page_ids == expected
