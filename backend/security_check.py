"""Bounded, offline security checks against the actual ASGI app and a temporary DB.

Run from backend: python security_check.py --output /path/to/report.json
Optional isolated browser fixture: python security_check.py --serve 8011
Exit codes: 0 = no findings, 1 = findings/warnings, 2 = check infrastructure failure.
"""

import argparse
import json
import os
import tempfile
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

XSS = '</textarea><svg onload="document.documentElement.dataset.securityXss=1"></svg>'
CANARY = "security-fixture-only-not-a-real-secret"


@dataclass
class Result:
    id: str
    title: str
    status: str
    severity: str
    evidence: dict
    recommendation: str


def row(db, model, **values):
    item = model(**values)
    db.add(item)
    db.flush()
    return item


def seed(engine, browser=False):
    from sqlalchemy.orm import Session

    from app.models import Participant, Proposal, Task, Team
    from app.schemas import Card
    from app.scoring import score_card

    with Session(engine) as db, db.begin():
        business = row(db, Participant, name="Fixture business", role="business", is_demo=True)
        team = row(db, Team, name="Fixture team", interests=["образование"], skills=["аналитика"])
        card = Card(
            title=f"Проверка {XSS}" if browser else "Security fixture task",
            topic="образование",
            context="Сотрудники собирают сведения о посещаемости вручную в бумажном журнале.",
            need="Нужен общий журнал посещаемости с отчётами для руководителя и родителей.",
            users="Руководитель центра, преподаватели и родители учеников.",
            data="Есть таблица посещений за два месяца и расписание занятий.",
            constraints="Учебный проект на четыре недели, только обезличенные сведения.",
            expected_result="Веб-форма отметки посещений и отчёт по каждой группе.",
            success_criteria="Отметка посещения занимает не более 1 минуты.",
            contact="fixture@example.test",
            interaction_format="Созвон раз в неделю и обсуждение прототипа.",
        )
        if browser:
            for field in Card.model_fields:
                if field != "topic":
                    setattr(card, field, f"Проверка {XSS}")
            business.name = f"Заказчик {XSS}"
            team.name = f"Команда {XSS}"
        scored = score_card(card)
        task = row(
            db,
            Task,
            **card.model_dump(),
            confirmed=True,
            score=scored.score,
            level=scored.level,
            owner_id=business.id,
        )
        draft = row(
            db,
            Task,
            title="Private fixture draft",
            topic="образование",
            contact=CANARY,
            confirmed=False,
            owner_id=business.id,
        )
        proposal = row(
            db,
            Proposal,
            task_id=task.id,
            team_id=team.id,
            idea=f"Идея {XSS}" if browser else "Создать учебный журнал посещений",
            plan=f"План {XSS}" if browser else "Прототип, проверка с бизнесом и запуск",
            deadline=date.today() + timedelta(days=7),
            prototype_url="https://example.test/prototype",
        )
        return {"task": task.id, "draft": draft.id, "team": team.id, "proposal": proposal.id}


@contextmanager
def isolated_app(browser=False):
    # Apply before importing main: its module-level app must not open the real DB.
    with tempfile.TemporaryDirectory(prefix="ghosttech-security-") as folder:
        environment = {
            "DATABASE_URL": f"sqlite:///{Path(folder) / 'security.sqlite3'}",
            "AI_MODE": "demo",
            "OPENAI_API_KEY": "",
            "AI_TIMEOUT_SECONDS": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        with patch.dict(os.environ, environment):
            import ai
            from app.cli import migrate
            from app.config import Settings
            from app.main import create_app

            settings = Settings(
                _env_file=None,
                **{
                    key.lower(): value
                    for key, value in environment.items()
                    if key != "PYTHONDONTWRITEBYTECODE"
                },
            )
            app = create_app(settings)
            migrate(app.state.engine)
            ids = seed(app.state.engine, browser=browser)
            # Fail closed if application changes unexpectedly try to call a real provider.
            with patch.object(ai, "call_model", side_effect=AssertionError("External AI disabled")):
                try:
                    yield app, ids
                finally:
                    app.state.engine.dispose()


def audit():
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.models import Proposal, Task

    results = []

    def check(identifier, title, severity, probe, recommendation="", warning=False):
        try:
            protected, evidence = probe()
            status = "PASS" if protected else "WARN" if warning else "FAIL"
        except Exception as error:
            # Do not dump response bodies, local config, or credentials into the report.
            status, evidence = "ERROR", {"exception_type": type(error).__name__}
        results.append(Result(identifier, title, status, severity, evidence, recommendation))

    with isolated_app() as (app, ids), TestClient(app, raise_server_exceptions=False) as client:
        business = TestClient(app, raise_server_exceptions=False)
        student = TestClient(app, raise_server_exceptions=False)
        authorized = None

        def authorized_fixture():
            nonlocal authorized
            if authorized is not None:
                return authorized
            for actor, email, role in (
                (business, "security-business@example.test", "business"),
                (student, "security-student@example.test", "student"),
            ):
                response = actor.post(
                    "/api/auth/register",
                    json={
                        "email": email,
                        "name": role,
                        "role": role,
                        "password": "SecurityFixturePassword1!",
                    },
                )
                if response.status_code != 201:
                    raise RuntimeError("Fixture registration failed")
            team_response = student.post("/api/teams", json={"name": "Security student team"})
            task_response = business.post(
                "/api/tasks",
                json={
                    "card": {"title": "Authorized fixture", "topic": "образование"},
                    "confirmed": True,
                },
            )
            if team_response.status_code != 201 or task_response.status_code != 201:
                raise RuntimeError("Fixture team or task creation failed")
            team_id = team_response.json()["id"]
            task_id = task_response.json()["id"]
            proposal_response = student.post(
                f"/api/tasks/{task_id}/proposals",
                json={
                    "team_id": team_id,
                    "idea": "Authorized fixture idea",
                    "plan": "Authorized fixture plan",
                    "deadline": str(date.today() + timedelta(days=7)),
                    "prototype_url": "https://example.test/prototype",
                },
            )
            if proposal_response.status_code != 201:
                raise RuntimeError("Fixture proposal creation failed")
            proposal_id = proposal_response.json()["id"]
            decision = business.patch(
                f"/api/proposals/{proposal_id}/decision", json={"decision": "accepted"}
            )
            if decision.status_code != 200:
                raise RuntimeError("Fixture proposal acceptance failed")
            authorized = {"team": team_id, "task": task_id, "proposal": proposal_id}
            return authorized

        def unauthorized(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            return response.status_code in {401, 403, 404}, {
                "method": method,
                "path": path,
                "status": response.status_code,
                "credentials_supplied": False,
            }

        def modify_task():
            protected, evidence = unauthorized(
                "PATCH", f"/api/tasks/{ids['task']}", json={"confirmed": False}
            )
            with Session(app.state.engine) as db, db.begin():
                task = db.get(Task, ids["task"])
                changed = not task.confirmed
                task.confirmed = True  # Restore fixture for independent downstream probes.
            evidence["database_changed"] = changed
            return protected and not changed, evidence

        check(
            "AUTH-01",
            "Изменение чужой задачи без входа",
            "high",
            modify_task,
            "Проверять сессию, роль business и владельца задачи на сервере.",
        )
        check(
            "AUTH-02",
            "Изменение чужой команды без входа",
            "high",
            lambda: unauthorized(
                "PATCH", f"/api/teams/{ids['team']}", json={"name": "Changed anonymously"}
            ),
            "Разрешать редактирование только участникам соответствующей команды.",
        )
        check(
            "AUTH-03",
            "Решение по чужому отклику без входа",
            "high",
            lambda: unauthorized(
                "PATCH", f"/api/proposals/{ids['proposal']}/decision", json={"decision": "accepted"}
            ),
            "Проверять владельца задачи при принятии и отклонении отклика.",
        )
        # Seed the accepted state independently; this check still works once AUTH-03 is fixed.
        with Session(app.state.engine) as db, db.begin():
            db.get(Proposal, ids["proposal"]).status = "accepted"
        check(
            "AUTH-04",
            "Начисление баллов без входа",
            "high",
            lambda: unauthorized(
                "POST", f"/api/proposals/{ids['proposal']}/progress", json={"stage": "prototype"}
            ),
            "Начислять баллы только после действия авторизованного владельца задачи.",
        )

        def impersonate_team():
            with Session(app.state.engine) as db, db.begin():
                target = row(
                    db, Task, title="Separate fixture", topic="образование", confirmed=True
                )
                task_id = target.id
            return unauthorized(
                "POST",
                f"/api/tasks/{task_id}/proposals",
                json={
                    "team_id": ids["team"],
                    "idea": "Отправлено без участия владельца команды",
                    "plan": "Проверить доступ к чужому профилю команды",
                    "deadline": str(date.today() + timedelta(days=7)),
                    "prototype_url": "https://example.test/prototype",
                },
            )

        check(
            "AUTH-05",
            "Отклик от имени чужой команды",
            "high",
            impersonate_team,
            "Получать команду из проверенного членства пользователя, а не доверять team_id.",
        )

        def private_drafts():
            listing = client.get("/api/tasks", params={"include_drafts": True})
            detail = client.get(f"/api/tasks/{ids['draft']}")
            listed = listing.status_code == 200 and any(
                x["id"] == ids["draft"] for x in listing.json()
            )
            disclosed = detail.status_code == 200 and CANARY in detail.text
            return not listed and not disclosed, {
                "draft_listed": listed,
                "draft_contact_disclosed": disclosed,
            }

        check(
            "DATA-01",
            "Чтение неопубликованных карточек",
            "high",
            private_drafts,
            "Фильтровать include_drafts по владельцу и закрыть прямое чтение чужого черновика.",
        )

        def cors():
            response = client.options(
                "/api/tasks",
                headers={
                    "Origin": "https://untrusted.example",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            return (
                response.status_code == 400
                and "access-control-allow-origin" not in response.headers,
                {
                    "preflight_status": response.status_code,
                },
            )

        check("CORS-01", "Запрет CORS для постороннего сайта", "medium", cors)

        def simple_cross_origin():
            import app.main as main

            original = main.analyze_task
            with patch.object(main, "analyze_task", wraps=original) as operation:
                response = client.post(
                    "/api/tasks/analyze",
                    content=json.dumps(
                        {
                            "draft_text": "Нужен журнал посещаемости для учебного центра",
                            "topic": "образование",
                        }
                    ),
                    headers={"Content-Type": "text/plain", "Origin": "https://untrusted.example"},
                )
            return operation.call_count == 0, {
                "status": response.status_code,
                "handler_calls": operation.call_count,
                "content_type": "text/plain",
                "cors_response_readable": "access-control-allow-origin" in response.headers,
            }

        check(
            "ORIGIN-01",
            "Посторонний Origin запускает обработку через text/plain",
            "medium",
            simple_cross_origin,
            "Для изменяющих состояние и платных операций проверять сессию, "
            "Origin/CSRF и Content-Type. CORS сам по себе не блокирует выполнение простого POST.",
        )

        def ai_access():
            import ai

            output = {
                "questions": [
                    {"id": "q1", "field": "data", "question": "Какие материалы доступны?"},
                    {"id": "q2", "field": "users", "question": "Кто пользуется системой?"},
                    {"id": "q3", "field": "constraints", "question": "Какие есть ограничения?"},
                ]
            }
            with (
                patch.object(ai, "get_mode", return_value="ai"),
                patch.object(ai, "call_model", return_value=output) as provider,
            ):
                statuses = [
                    client.post(
                        "/api/tasks/analyze",
                        json={
                            "draft_text": "Нужен журнал посещаемости для учебного центра",
                            "topic": "образование",
                        },
                    ).status_code
                    for _ in range(5)
                ]
            return provider.call_count == 0, {
                "requests": 5,
                "statuses": statuses,
                "mock_provider_calls": provider.call_count,
                "real_provider_calls": 0,
            }

        check(
            "RESOURCE-01",
            "Доступ к провайдеру ИИ без аккаунта",
            "high",
            ai_access,
            "Перед подключением платного API добавить серверную авторизацию, лимит запросов "
            "и квоту стоимости. Пять запросов не являются нагрузочным тестом.",
        )

        def sensitive_files():
            paths = [
                "/.env",
                "/backend/.env",
                "/.git/config",
                "/backend/data/app.sqlite3",
                "/static/..%2F.env",
                "/static/%2e%2e%2fbackend%2f.env",
                "/static/%2e%2e%2f.git%2fconfig",
            ]
            codes = {path: client.get(path).status_code for path in paths}
            return all(code in {400, 403, 404} for code in codes.values()), codes

        check("FILES-01", "Недоступность .env, Git и БД через HTTP", "high", sensitive_files)

        def sqli():
            payloads = ["' OR 1=1 --", "'; DROP TABLE tasks; --", '" UNION SELECT 1 --', "%_"]
            observations = []
            for value in payloads:
                response = client.get("/api/tasks", params={"search": value})
                observations.append(
                    {
                        "status": response.status_code,
                        "empty": response.status_code == 200 and response.json() == [],
                    }
                )
            with Session(app.state.engine) as db:
                intact = db.get(Task, ids["task"]) is not None
            return intact and all(item["empty"] for item in observations), {
                "cases": observations,
                "fixture_intact": intact,
            }

        check("SQL-01", "SQL-инъекция в поиске каталога", "high", sqli)

        def dangerous_links():
            owned = authorized_fixture()
            payload = {
                "team_id": owned["team"],
                "idea": "Проверка схемы ссылки",
                "plan": "Проверка схемы ссылки",
                "deadline": str(date.today() + timedelta(days=7)),
            }
            links = [
                "javascript:alert(1)",
                "data:text/html,<script>alert(1)</script>",
                "file:///etc/passwd",
                "vbscript:msgbox(1)",
            ]
            codes = [
                student.post(
                    f"/api/tasks/{owned['task']}/proposals",
                    json={**payload, "prototype_url": link},
                ).status_code
                for link in links
            ]
            return all(code == 422 for code in codes), {"statuses": codes}

        check("URL-01", "Запрет исполняемых схем ссылок на прототип", "high", dangerous_links)

        def mass_assignment():
            owned = authorized_fixture()
            responses = [
                business.post("/api/tasks", json={"card": {}, "score": 100}),
                student.post("/api/teams", json={"name": "Fixture", "points": 99999}),
                business.patch(f"/api/tasks/{owned['task']}", json={"owner_id": "attacker"}),
            ]
            codes = [response.status_code for response in responses]
            return all(code == 422 for code in codes), {"statuses": codes}

        check("INPUT-01", "Запрет подмены вычисляемых полей", "high", mass_assignment)

        def invalid_input():
            authorized_fixture()
            responses = [
                business.post(
                    "/api/tasks/analyze", content="{", headers={"Content-Type": "application/json"}
                ),
                business.post(
                    "/api/tasks/analyze", json={"draft_text": "x" * 3001, "topic": "образование"}
                ),
                business.post("/api/tasks", json={"card": {"title": "x" * 201}}),
                client.get("/api/tasks", params={"limit": 100000}),
                client.get("/api/tasks", params={"offset": -1}),
            ]
            codes = [response.status_code for response in responses]
            return all(code == 422 for code in codes) and not any(
                "Traceback" in response.text for response in responses
            ), {"statuses": codes}

        check("INPUT-02", "Границы входных данных и безопасные ошибки", "medium", invalid_input)

        def double_points():
            owned = authorized_fixture()
            path = f"/api/proposals/{owned['proposal']}/progress"
            first = business.post(path, json={"stage": "testing"})
            second = business.post(path, json={"stage": "testing"})
            with Session(app.state.engine) as db:
                from app.models import Progress

                points = list(
                    db.scalars(
                        select(Progress).where(
                            Progress.proposal_id == owned["proposal"], Progress.stage == "testing"
                        )
                    )
                )
            return first.status_code == 201 and second.status_code == 409 and len(points) == 1, {
                "first_status": first.status_code,
                "repeat_status": second.status_code,
                "awards": len(points),
            }

        check("LOGIC-01", "Защита от повторного начисления баллов", "medium", double_points)

        def frame_policy():
            response = client.get("/")
            csp = response.headers.get("content-security-policy", "")
            xfo = response.headers.get("x-frame-options", "")
            framing = next(
                (
                    part.strip().lower()
                    for part in csp.split(";")
                    if part.strip().lower().startswith("frame-ancestors ")
                ),
                "",
            )
            return framing in {
                "frame-ancestors 'none'",
                "frame-ancestors 'self'",
            } or xfo.lower() in {"deny", "sameorigin"}, {
                "content_security_policy": csp,
                "x_frame_options": xfo,
            }

        check(
            "HEADER-01",
            "Защита интерфейса от встраивания в чужой iframe",
            "medium",
            frame_policy,
            "Добавить CSP frame-ancestors 'none' или 'self' и/или X-Frame-Options. "
            "Проверка относится к приложению, не к будущему reverse proxy.",
        )

        def nosniff():
            value = client.get("/").headers.get("x-content-type-options")
            return value == "nosniff", {"x_content_type_options": value}

        check(
            "HEADER-02",
            "Запрет MIME-sniffing",
            "low",
            nosniff,
            "Добавить X-Content-Type-Options: nosniff.",
            warning=True,
        )

        def health_privacy():
            response = client.get("/api/health")
            fields = set(response.json())
            return response.status_code == 200 and fields <= {
                "status",
                "mode",
                "database",
                "ai_configured",
            } and CANARY not in response.text, {"fields": sorted(fields)}

        check("DATA-02", "Health не раскрывает ключи и настройки БД", "medium", health_privacy)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": (
            "app.main.create_app; temporary SQLite database; "
            "no real AI requests; no production data writes"
        ),
        "policy": (
            "Public demo records are read-only. Changes require an authenticated "
            "account, matching role and ownership; assistant calls have a daily account quota."
        ),
        "limitations": [
            "Not a penetration-test certification",
            "No load/DoS testing",
            "No real model prompt-injection evaluation",
            "Dependency advisories and browser XSS checks are separate",
        ],
        "counts": dict(Counter(result.status for result in results)),
        "checks": [asdict(result) for result in results],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON report destination")
    parser.add_argument(
        "--serve", type=int, metavar="PORT", help="Serve isolated XSS fixture on 127.0.0.1 only"
    )
    args = parser.parse_args()
    if args.serve is not None:
        if not 1024 <= args.serve <= 65535:
            parser.error("PORT must be between 1024 and 65535")
        import uvicorn

        with isolated_app(browser=True) as (app, _):
            print(f"Disposable browser fixture: http://127.0.0.1:{args.serve}", flush=True)
            uvicorn.run(app, host="127.0.0.1", port=args.serve, log_level="warning")
        return 0
    report = audit()
    for item in report["checks"]:
        print(f"{item['status']:5} {item['id']:12} {item['title']}")
    print(json.dumps(report["counts"], ensure_ascii=False))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return (
        2
        if report["counts"].get("ERROR")
        else 1
        if report["counts"].get("FAIL") or report["counts"].get("WARN")
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
