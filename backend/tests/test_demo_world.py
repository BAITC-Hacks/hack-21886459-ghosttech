import json

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api import create_app
from app.cli import migrate
from app.config import BACKEND_DIR, ROOT_DIR, Settings
from app.database import create_db_engine
from app.models import Participant, Progress, Proposal, Task, Team
from app.seed import seed_database


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path / 'demo.db'}", ai_mode="demo"
    )
    engine = create_db_engine(settings)
    migrate(engine)
    with Session(engine) as db, db.begin():
        seed_database(db)
    engine.dispose()
    with TestClient(create_app(settings)) as client:
        yield client


def test_demo_relationships_and_readiness(client):
    people = client.get("/api/participants?limit=100").json()
    assert len(people) == len({person["name"] for person in people}) == 100
    businesses = [person for person in people if person["role"] == "business"]
    assert len(businesses) == 20
    assert all(person["is_demo"] for person in people)
    assert all(person["team_id"] for person in people if person["role"] == "student")
    tasks = client.get("/api/tasks?limit=100").json()
    demo = [task for task in tasks if task["is_demo"]]
    assert len(demo) == len({task["title"] for task in demo}) == 80
    assert {task["level"] for task in demo} == {"draft", "working", "ready", "priority"}
    assert all(task["owner"]["role"] == "business" for task in demo)
    assert all(task["topic"] in task["owner"]["interests"] for task in demo)
    teams = client.get("/api/teams?limit=100").json()
    for team in [team for team in teams if team["is_demo"]]:
        assert len(team["members"]) == 4
        proposals = client.get("/api/proposals", params={"team_id": team["id"]}).json()
        assert team["points"] == sum(
            {"prototype": 10, "testing": 20, "final": 30}[stage]
            for proposal in proposals
            for stage in proposal["stages_done"]
        )
    topics = client.get("/api/topics").json()
    assert sum(topic["tasks_count"] for topic in topics) == 85
    for topic in topics:
        filtered = client.get("/api/tasks", params={"topic": topic["topic"], "limit": 100}).json()
        assert len(filtered) == topic["tasks_count"]
        assert all(task["topic"] == topic["topic"] for task in filtered)


def test_people_filters_pagination_search_and_business_view(client):
    all_students = client.get("/api/participants?role=student&limit=100").json()
    assert len(all_students) == 80
    assert (
        client.get("/api/participants?role=student&offset=20&limit=20").json()
        == all_students[20:40]
    )
    owner = client.get("/api/participants?role=business").json()[0]
    tasks = client.get("/api/tasks", params={"owner_id": owner["id"]}).json()
    assert len(tasks) >= 3
    assert all(task["owner"]["id"] == owner["id"] for task in tasks)
    results = client.get("/api/tasks", params={"search": "МАКУЛАТУРЫ"}).json()
    assert [task["title"] for task in results] == ["Учёт сбора макулатуры"]
    assert client.get("/api/tasks", params={"search": "__%"}).json() == []
    assert client.get("/api/participants?role=admin").status_code == 422
    assert client.get("/api/participants?limit=101").status_code == 422


def test_create_task_as_demo_business_and_preserve_author_on_edit(client):
    payload = {"card": {"title": "Проверка публикации", "topic": "услуги"}, "confirmed": True}
    response = client.post("/api/tasks", json={**payload, "owner_id": "demo-business-07"})
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["is_demo"] and task["owner"]["id"] == "demo-business-07"
    edited = client.patch(f"/api/tasks/{task['id']}", json=payload).json()
    assert edited["owner"] == task["owner"]
    assert (
        client.post("/api/tasks", json={**payload, "owner_id": "demo-student-01"}).status_code
        == 422
    )
    assert client.post("/api/tasks", json={**payload, "owner_id": "missing"}).status_code == 404
    personal = client.post("/api/tasks", json=payload).json()
    assert personal["owner"] is None and personal["is_demo"] is False


def test_reseed_preserves_edits_decisions_and_earned_points(client):
    with Session(client.app.state.engine) as db, db.begin():
        proposal = db.scalar(
            select(Proposal).where(Proposal.id.like("demo-%"), Proposal.status == "pending")
        )
        proposal.status = "rejected"
        proposal_id = proposal.id
        db.get(Task, "demo-task-001").title = "Отредактировано пользователем"
        db.get(Participant, "demo-business-01").bio = "Изменённое описание"
        db.get(Team, "demo-team-01").name = "Изменённая команда"
        db.delete(db.scalar(select(Progress)))
        before = len(db.scalars(select(Progress)).all())
    with Session(client.app.state.engine) as db, db.begin():
        assert not any(seed_database(db).values())
        assert db.get(Proposal, proposal_id).status == "rejected"
        assert db.get(Task, "demo-task-001").title == "Отредактировано пользователем"
        assert db.get(Participant, "demo-business-01").bio == "Изменённое описание"
        assert db.get(Team, "demo-team-01").name == "Изменённая команда"
        assert len(db.scalars(select(Progress)).all()) == before


def test_populated_0002_migration_preserves_existing_records(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'upgrade.db'}")
    engine = create_db_engine(settings)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0002")
        connection.execute(
            text("INSERT INTO teams VALUES ('old-team', 'Existing', '[]', '[]', '[]', 37)")
        )
        card = json.loads((ROOT_DIR / "sample_data/cards.json").read_text())[0]["card"]
        params = dict(
            id="old-task",
            **card,
            confirmed=1,
            score=82,
            level="ready",
            created_at="2026-09-01",
            updated_at="2026-09-01",
        )
        connection.execute(
            text(
                f"INSERT INTO tasks ({', '.join(params)}) "
                f"VALUES ({', '.join(':' + key for key in params)})"
            ),
            params,
        )
        connection.execute(
            text(
                "INSERT INTO proposals VALUES ('old-proposal', 'old-task', 'old-team', "
                "'Keep idea', 'Keep plan', '2026-12-01', '', 'accepted', '2026-09-02')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO progress VALUES "
                "('old-progress', 'old-proposal', 'prototype', 10, '2026-09-03')"
            )
        )
        connection.commit()
    migrate(engine)
    with Session(engine) as db:
        task = db.get(Task, "old-task")
        assert task.title == card["title"] and task.owner is None and not task.is_demo
        assert task.work_tags == []
        assert db.get(Team, "old-team").base_points == 37
        assert db.get(Proposal, "old-proposal").idea == "Keep idea"
        assert db.get(Progress, "old-progress").points == 10
        assert not db.execute(text("PRAGMA foreign_key_check")).all()
    engine.dispose()
