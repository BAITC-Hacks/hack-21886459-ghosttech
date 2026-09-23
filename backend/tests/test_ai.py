from fastapi.testclient import TestClient

import ai
from ai import AIError, analyze_task, build_card, check_invented
from ai_demo import analyze_demo, build_card_demo
from schemas_ai import AnalyzeInput, AnswerInput, BuildCardInput


def test_analyze_demo_questions_and_filled_fields():
    result = analyze_demo(
        "Хотим навести порядок с посещаемостью кружков, сейчас всё в бумажном журнале.",
        "образование",
    )
    assert len(result["questions"]) >= 3
    assert result["questions"][0]["field"] == "data"
    assert {"need", "context"}.issubset(result["filled_fields"])


def test_build_card_demo_uses_answers_without_inventing_numbers():
    result = build_card_demo(
        "Нужно вести журнал посещаемости.",
        "образование",
        [AnswerInput(question_id="q1", field="data", answer="журналы за сентябрь")],
    )
    assert result["card"]["data"] == "Журналы за сентябрь."
    assert result["card"]["topic"] == "образование"
    assert not any("за 2" in warning for warning in result["warnings"])


def test_check_invented_warns_about_missing_number():
    warnings = check_invented(
        {"title": "Задача", "context": "за 2 недели", "need": "", "data": "", "expected_result": "", "success_criteria": "", "constraints": "", "users": "", "contact": "", "interaction_format": "", "topic": "образование"},
        "Нужно улучшить процесс без срока.",
        [],
    )
    assert any("Контекст" in warning and "2" in warning for warning in warnings)


def test_model_retries_after_invalid_json(monkeypatch):
    responses = iter([{"questions": []}, {"questions": [{"id": "x", "field": "data", "question": "Какие данные есть?"}], "filled_fields": [], "missing_fields": ["data"]}])
    monkeypatch.setattr(ai, "get_mode", lambda: "ai")
    monkeypatch.setattr(ai, "ANALYZE_PROMPT", "prompt")
    monkeypatch.setattr(ai, "call_model", lambda *_args: next(responses))
    result = analyze_task(AnalyzeInput(draft_text="Достаточно длинное описание задачи", topic="образование"))
    assert result.mode == "ai"
    assert len(result.questions) >= 3


def test_model_failure_falls_back_to_demo(monkeypatch):
    monkeypatch.setattr(ai, "get_mode", lambda: "ai")
    monkeypatch.setattr(ai, "BUILD_CARD_PROMPT", "prompt")
    monkeypatch.setattr(ai, "call_model", lambda *_args: (_ for _ in ()).throw(AIError("offline")))
    result = build_card(BuildCardInput(draft_text="Нужно улучшить процесс работы.", topic="ритейл"))
    assert result.mode == "demo"
    assert any("демо-режим" in warning for warning in result.warnings)


def test_model_one_question_is_completed(monkeypatch):
    monkeypatch.setattr(ai, "get_mode", lambda: "ai")
    monkeypatch.setattr(ai, "ANALYZE_PROMPT", "prompt")
    monkeypatch.setattr(ai, "call_model", lambda *_args: {"questions": [{"id": "q1", "field": "data", "question": "Какие данные есть?"}], "filled_fields": [], "missing_fields": ["data"]})
    result = analyze_task(AnalyzeInput(draft_text="Достаточно длинное описание задачи", topic="образование"))
    assert len(result.questions) == 3


def test_analyze_endpoint_rejects_short_draft():
    from app.main import app

    with TestClient(app) as client:
        response = client.post("/api/tasks/analyze", json={"draft_text": "ок", "topic": "образование"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
