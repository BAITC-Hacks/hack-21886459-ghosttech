import json
import logging
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import ai
from ai import AIError, analyze_task, build_card, check_invented
from ai_demo import analyze_demo, build_card_demo
from schemas_ai import CARD_FIELDS, AnalyzeInput, AnswerInput, BuildCardInput

DRAFT = "Нужно улучшить процесс работы."
INPUT = {"draft_text": DRAFT, "topic": "образование"}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("AI_MODE", "demo")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")


def enable_ai(monkeypatch, fake):
    monkeypatch.setattr(ai, "get_mode", lambda: "ai")
    monkeypatch.setattr(ai, "ANALYZE_PROMPT", "prompt")
    monkeypatch.setattr(ai, "BUILD_CARD_PROMPT", "prompt")
    monkeypatch.setattr(ai, "call_model", fake)


def one_question():
    return {"questions": [{"id": "q1", "field": "data", "question": "Какие данные есть?"}]}


@pytest.fixture
def client(tmp_path):
    from app.cli import migrate
    from app.config import Settings
    from app.main import create_app

    app = create_app(
        Settings(
            _env_file=None, ai_mode="demo", database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}"
        )
    )
    migrate(app.state.engine)
    with TestClient(app) as client:
        yield client


def test_analyze_demo_questions_and_filled_fields():
    result = analyze_demo(
        "Хотим навести порядок с посещаемостью кружков, сейчас всё в бумажном журнале.",
        "образование",
    )
    assert 3 <= len(result["questions"]) <= 5
    # Per the keyword contract, "журнал" already supplies data.
    assert result["questions"][0]["field"] == "expected_result"
    assert {"need", "context", "data"}.issubset(result["filled_fields"])
    assert analyze_demo(DRAFT, "образование")["questions"][0]["field"] == "data"


def test_build_card_demo_uses_answers_without_inventing_numbers():
    result = build_card_demo(
        "Нужно вести журнал посещаемости.",
        "образование",
        [AnswerInput(question_id="q1", field="data", answer="журналы за сентябрь")],
    )
    assert result["card"]["data"] == "Журналы за сентябрь."
    assert result["card"]["topic"] == "образование"
    assert not any("которого нет" in warning for warning in result["warnings"])


def test_check_invented_warns_about_missing_facts():
    warnings = check_invented(
        {
            "context": "за 2 недели",
            "contact": "x@example.org",
            "data": "https://example.org/file",
            "topic": "2026",
        },
        DRAFT,
        [],
    )
    for fact in ("2", "x@example.org", "https://example.org/file"):
        assert any(fact in warning and "которого нет" in warning for warning in warnings)
    assert not any("2026" in warning for warning in warnings)
    assert len(warnings) == len(set(warnings))


@pytest.mark.parametrize("invalid", [{"questions": []}, json.JSONDecodeError("bad", "x", 0)])
def test_model_retries_after_invalid_response(monkeypatch, invalid):
    calls = []

    def fake(prompt, payload):
        calls.append(payload)
        if len(calls) == 1:
            if isinstance(invalid, Exception):
                raise invalid
            return invalid
        return one_question()

    enable_ai(monkeypatch, fake)
    result = analyze_task(AnalyzeInput(**INPUT))
    assert result.mode == "ai" and len(result.questions) == 3
    assert len(calls) == 2
    assert "correction" not in calls[0] and "correction" in calls[1]


@pytest.mark.parametrize("operation", ["analyze", "build"])
def test_provider_failure_falls_back_without_retry(monkeypatch, caplog, operation):
    calls = []

    def fake(*args):
        calls.append(args)
        raise AIError("secret response must not be logged")

    enable_ai(monkeypatch, fake)
    with caplog.at_level(logging.WARNING):
        result = (
            analyze_task(AnalyzeInput(**INPUT))
            if operation == "analyze"
            else build_card(BuildCardInput(**INPUT))
        )
    assert result.mode == "demo" and len(calls) == 1
    assert ai.AI_WARNING in caplog.text
    assert "secret response" not in caplog.text
    if operation == "build":
        assert ai.AI_WARNING in result.warnings


def test_model_one_question_is_completed(monkeypatch):
    enable_ai(monkeypatch, lambda *_: one_question())
    result = analyze_task(AnalyzeInput(**INPUT))
    assert result.mode == "ai"
    assert [q.field for q in result.questions] == ["data", "expected_result", "success_criteria"]


def test_question_ids_and_missing_field_priority(monkeypatch):
    raw = {
        "questions": [
            {"id": "q2", "field": "need", "question": "Потребность?"},
            {"id": "q2", "field": "users", "question": "Пользователи?"},
        ],
        "filled_fields": ["data"],
        "missing_fields": ["expected_result"],
    }
    enable_ai(monkeypatch, lambda *_: raw)
    result = analyze_task(AnalyzeInput(**INPUT))
    assert [q.id for q in result.questions] == ["q1", "q2", "q3"]
    assert result.questions[-1].field == "expected_result"


def test_two_invalid_responses_fall_back(monkeypatch):
    calls = []

    def fake(*args):
        calls.append(args)
        return {"questions": []}

    enable_ai(monkeypatch, fake)
    assert analyze_task(AnalyzeInput(**INPUT)).mode == "demo"
    assert len(calls) == 2


def test_build_normalises_and_skips_empty_answers(monkeypatch):
    def fake(prompt, payload):
        assert payload["answers"] == []
        return {
            "card": {"title": "  Задача  ", "topic": "другая", "data": 42, "users": None},
            "warnings": ["Проверьте", "Проверьте"],
        }

    enable_ai(monkeypatch, fake)
    result = build_card(
        BuildCardInput(
            **INPUT,
            answers=[
                {"question_id": "q1", "field": "data", "answer": "   "},
            ],
        )
    )
    assert result.mode == "ai" and set(result.card) == set(CARD_FIELDS)
    assert result.card["title"] == "Задача" and result.card["topic"] == INPUT["topic"]
    assert result.card["data"] == "42" and result.card["users"] == ""
    assert any("42" in warning for warning in result.warnings)
    assert len(result.warnings) == len(set(result.warnings))


def test_build_retries_invalid_warnings(monkeypatch):
    calls = []

    def fake(prompt, payload):
        calls.append(payload)
        return {"card": {}, "warnings": "bad"} if len(calls) == 1 else {"card": {}}

    enable_ai(monkeypatch, fake)
    result = build_card(BuildCardInput(**INPUT))
    assert result.mode == "ai" and len(calls) == 2 and "correction" in calls[1]
    assert result.card["topic"] == INPUT["topic"]


@pytest.mark.parametrize("endpoint", ["analyze", "build-card"])
def test_endpoints_accept_valid_demo_request(client, endpoint):
    response = client.post(f"/api/tasks/{endpoint}", json=INPUT)
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "demo"
    if endpoint == "build-card":
        assert set(response.json()["card"]) == set(CARD_FIELDS)
    else:
        assert 3 <= len(response.json()["questions"]) <= 5


@pytest.mark.parametrize(
    "payload",
    [
        {**INPUT, "draft_text": "  ок  "},
        {**INPUT, "topic": " "},
        {**INPUT, "draft_text": "x" * 3001},
        {**INPUT, "topic": "x" * 61},
        {**INPUT, "answers": [{"question_id": "q", "field": "data", "answer": "x"}] * 11},
        {**INPUT, "answers": [{"question_id": "q", "field": "data", "answer": "x" * 1001}]},
        {**INPUT, "answers": [{"question_id": "q", "field": "title", "answer": "x"}]},
    ],
)
def test_endpoint_validation_is_russian(client, payload):
    response = client.post("/api/tasks/build-card", json=payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error" and "Поле" in error["message"]


def test_analyze_endpoint_rejects_short_draft(client):
    response = client.post("/api/tasks/analyze", json={**INPUT, "draft_text": "ок"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_malformed_json(client):
    response = client.post(
        "/api/tasks/analyze", content="{", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert "корректный JSON" in response.json()["error"]["message"]


def test_health_and_route_precedence(client):
    assert client.get("/api/health").json() == {"status": "ok", "mode": "demo"}
    for path in ("/api/health", "/api/tasks/analyze", "/api/tasks/build-card"):
        assert any(route.path == path for route in client.app.routes[:3])


def test_model_call_runs_outside_event_loop(client, monkeypatch):
    import app.main as main

    threads = []
    original = main.analyze_task

    def wrapped(data):
        threads.append(threading.get_ident())
        return original(data)

    monkeypatch.setattr(main, "analyze_task", wrapped)
    loop_thread = client.portal.call(threading.get_ident)
    assert client.post("/api/tasks/analyze", json=INPUT).status_code == 200
    assert threads and threads[0] != loop_thread


def test_missing_prompt_falls_back(monkeypatch, caplog):
    enable_ai(monkeypatch, lambda *_: pytest.fail("model must not be called"))
    monkeypatch.setattr(ai, "ANALYZE_PROMPT", None)
    monkeypatch.setattr(ai, "BUILD_CARD_PROMPT", None)
    with caplog.at_level(logging.WARNING):
        assert analyze_task(AnalyzeInput(**INPUT)).mode == "demo"
        result = build_card(BuildCardInput(**INPUT))
    assert result.mode == "demo" and ai.AI_WARNING in result.warnings
    assert ai.AI_WARNING in caplog.text


@pytest.mark.parametrize(
    "mode,key,expected",
    [
        ("auto", "", "demo"),
        ("auto", "test", "ai"),
        ("demo", "test", "demo"),
    ],
)
def test_mode(monkeypatch, mode, key, expected):
    monkeypatch.setenv("AI_MODE", mode)
    monkeypatch.setenv("OPENAI_API_KEY", key)
    assert ai.get_mode() == expected


def test_sdk_contract_without_network(monkeypatch, caplog):
    import openai

    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["config"] = kwargs
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            captured["closed"] = True

        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    monkeypatch.setattr(openai, "OpenAI", FakeClient)
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-key")
    with caplog.at_level(logging.INFO):
        assert ai.call_model("prompt", {"draft_text": DRAFT}) == {}
    assert captured["config"]["max_retries"] == 0
    assert captured["request"]["model"] == "test-model"
    assert captured["request"]["response_format"] == {"type": "json_object"}
    assert captured["request"]["timeout"] == 20
    assert json.loads(captured["request"]["messages"][1]["content"])["draft_text"] == DRAFT
    assert captured["closed"]
    assert "secret-test-key" not in caplog.text and DRAFT not in caplog.text


def test_extra_questions_are_trimmed(monkeypatch):
    raw = {
        "questions": [
            {"id": f"q{i}", "field": "data", "question": "Какие данные есть?"} for i in range(6)
        ]
    }
    enable_ai(monkeypatch, lambda *_: raw)
    result = analyze_task(AnalyzeInput(**INPUT))
    assert result.mode == "ai" and len(result.questions) == 5


def test_analysis_scores_only_facts_in_the_draft(client, monkeypatch):
    raw = {
        "summary": "Заказчик хочет улучшить рабочий процесс. Нужны данные и критерии приёмки.",
        "draft_card": {
            "title": "Улучшение процесса",
            "need": DRAFT,
            "data": "Есть база на 10000 клиентов",
            "topic": "чужая тема",
        },
        **one_question(),
    }
    enable_ai(monkeypatch, lambda *_: raw)
    response = client.post("/api/tasks/analyze", json=INPUT)
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "ai" and result["summary"] == raw["summary"]
    assert result["draft_card"]["need"] == DRAFT
    assert result["draft_card"]["data"] == ""
    assert result["draft_card"]["topic"] == INPUT["topic"]
    assert result["filled_fields"] == ["need"]
    assert "data" in result["missing_fields"]
    scored = client.post("/api/tasks/score", json={"card": result["draft_card"]}).json()
    assert result["score"] == scored
    assert result["warnings"]


def test_analyze_fallback_is_visible_to_the_user(client, monkeypatch):
    def unavailable(*_):
        raise AIError("offline")

    enable_ai(monkeypatch, unavailable)
    result = client.post("/api/tasks/analyze", json=INPUT).json()
    assert result["mode"] == "demo"
    assert ai.AI_WARNING in result["warnings"]
    assert "ключевым словам" in result["summary"]
    assert 0 <= result["score"]["score"] <= 100


def test_question_context_is_forwarded_for_short_answers(monkeypatch):
    question = "Нужен ли отчёт по списаниям хлеба за каждый день?"

    def fake(prompt, payload):
        assert payload["answers"][0]["question"] == question
        assert payload["answers"][0]["answer"] == "Да"
        return {"card": {"expected_result": "Отчёт по списаниям хлеба за каждый день"}}

    enable_ai(monkeypatch, fake)
    result = build_card(
        BuildCardInput(
            **INPUT,
            answers=[
                {
                    "question_id": "q1",
                    "field": "expected_result",
                    "question": question,
                    "answer": "Да",
                }
            ],
        )
    )
    assert result.mode == "ai"
    assert "хлеба" in result.card["expected_result"]


def test_live_output_schema_constrains_question_fields():
    schema = ai._response_format(ai.ANALYZE_PROMPT)["json_schema"]
    assert schema["strict"] is True
    properties = schema["schema"]["properties"]
    assert properties["questions"]["minItems"] == 3
    assert "topic" not in properties["filled_fields"]["items"]["enum"]
    assert set(properties["draft_card"]["required"]) == set(CARD_FIELDS)
