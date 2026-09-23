import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import ai_agents
from app.api import create_app
from app.cli import migrate
from app.config import Settings
from app.database import create_db_engine
from app.schemas import Card

DRAFT = {"draft_text": "Журнал посещений сейчас на бумаге", "topic": "образование"}
ANALYSIS = {
    "questions": [
        {"id": "q1", "field": "data", "question": "Какие материалы есть?"},
        {"id": "q2", "field": "users", "question": "Кто будет пользоваться решением?"},
        {"id": "q3", "field": "success_criteria", "question": "Как проверить результат?"},
    ],
    "filled_fields": ["context", "topic"],
    "missing_fields": ["data", "users", "success_criteria"],
}


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        ai_mode="openai",
        openai_api_key="sk-test-not-a-real-key",
    )
    engine = create_db_engine(settings)
    migrate(engine)
    engine.dispose()
    with TestClient(create_app(settings)) as client:
        yield client


def response_body(text):
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": "gpt-5.4-mini",
        "output": [
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }


@pytest.fixture
def provider(monkeypatch):
    """Exercise the real Agents SDK and OpenAI parser with an in-memory HTTP transport."""
    original = ai_agents.AsyncOpenAI
    requests = []

    def install(output=ANALYSIS, status=200, error=None, raw=None):
        def handle(request):
            requests.append(request)
            if error:
                raise error(request)
            if status != 200:
                return httpx.Response(
                    status,
                    json={"error": {"message": "sensitive-provider-detail", "type": "test"}},
                )
            return httpx.Response(
                200, json=response_body(raw if raw is not None else json.dumps(output))
            )

        def factory(**kwargs):
            return original(
                **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
            )

        monkeypatch.setattr(ai_agents, "AsyncOpenAI", factory)
        return requests

    return install


def test_real_sdk_analysis_contract_and_no_publication(client, provider):
    requests = provider()
    response = client.post("/api/tasks/analyze", json=DRAFT)
    assert response.status_code == 200, response.text
    assert response.json() == {**ANALYSIS, "mode": "openai"}
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.openai.com/v1/responses"
    payload = json.loads(request.content)
    assert payload["model"] == "gpt-5.4-mini"
    assert payload["store"] is False
    assert payload["max_output_tokens"] == 6000
    assert payload["tools"] == []
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert "mode" not in payload["text"]["format"]["schema"]["properties"]
    assert json.loads(payload["input"][-1]["content"]) == DRAFT
    assert client.get("/api/tasks?include_drafts=true").json() == []


def test_real_sdk_build_returns_card_and_review_warning(client, provider):
    card = Card(
        title="Журнал посещений",
        topic=DRAFT["topic"],
        context=DRAFT["draft_text"],
        data="Есть бумажный журнал",
    ).model_dump()
    requests = provider({"card": card, "warnings": ["Не указаны критерии успеха."]})
    body = {
        **DRAFT,
        "answers": [{"question_id": "q1", "field": "data", "answer": card["data"]}],
    }
    response = client.post("/api/tasks/build-card", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["card"] == card
    assert result["card"]["contact"] == result["card"]["success_criteria"] == ""
    assert result["mode"] == "openai"
    assert ai_agents.REVIEW_WARNING in result["warnings"]
    assert json.loads(json.loads(requests[0].content)["input"][-1]["content"]) == body
    assert client.get("/api/tasks?include_drafts=true").json() == []


@pytest.mark.parametrize(
    "mode, key, expected",
    [
        ("auto", "", "demo"),
        ("auto", "  ", "demo"),
        ("auto", "test", "openai"),
        ("demo", "test", "demo"),
        ("openai", "", "openai"),
    ],
)
def test_mode_selection(mode, key, expected):
    settings = Settings(_env_file=None, ai_mode=mode, openai_api_key=key)
    assert settings.assistant_mode == expected


def test_forced_openai_without_key_and_health_do_not_call_provider(client, provider):
    requests = provider()
    client.app.state.settings.openai_api_key = SecretStr("")
    health = client.get("/api/health")
    assert health.json()["mode"] == "openai"
    assert health.json()["ai_configured"] is False
    response = client.post("/api/tasks/analyze", json=DRAFT)
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]
    assert not requests


def test_explicit_demo_preserves_draft_with_blank_answers(client, provider):
    requests = provider()
    client.app.state.settings.ai_mode = "demo"
    result = client.post("/api/tasks/analyze", json=DRAFT).json()
    assert result["mode"] == "demo"
    built = client.post(
        "/api/tasks/build-card",
        json={**DRAFT, "answers": [{"question_id": "q1", "field": "context", "answer": ""}]},
    ).json()
    assert built["card"]["context"] == DRAFT["draft_text"]
    assert built["mode"] == "demo"
    assert not requests


@pytest.mark.parametrize("status, expected", [(401, 503), (403, 503), (429, 429), (500, 502)])
@pytest.mark.parametrize("endpoint", ["analyze", "build-card"])
def test_provider_errors_are_safe_and_never_silent_demo(
    client, provider, status, expected, endpoint
):
    requests = provider(status=status)
    response = client.post(f"/api/tasks/{endpoint}", json=DRAFT)
    assert response.status_code == expected
    assert "detail" in response.json()
    assert "sensitive-provider-detail" not in response.text
    assert "sk-test-not-a-real-key" not in response.text
    assert len(requests) == 1


@pytest.mark.parametrize("error, expected", [(httpx.ReadTimeout, 504), (httpx.ConnectError, 502)])
def test_network_errors(client, provider, error, expected):
    provider(error=lambda request: error("internal details", request=request))
    response = client.post("/api/tasks/analyze", json=DRAFT)
    assert response.status_code == expected
    assert "internal details" not in response.text


def test_total_timeout_cancels_agent(client, monkeypatch):
    async def slow_run(*args, **kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(ai_agents.Runner, "run", slow_run)
    client.app.state.settings.ai_timeout_seconds = 0.01
    assert client.post("/api/tasks/analyze", json=DRAFT).status_code == 504


@pytest.mark.parametrize("raw", ["not json", "{}", "[]"])
@pytest.mark.parametrize("endpoint", ["analyze", "build-card"])
def test_invalid_structured_output(client, provider, raw, endpoint):
    provider(raw=raw)
    response = client.post(f"/api/tasks/{endpoint}", json=DRAFT)
    assert response.status_code == 502


@pytest.mark.parametrize(
    "kind", ["few", "many", "duplicate_id", "duplicate_field", "overlap", "unknown"]
)
def test_invalid_analysis_is_rejected(client, provider, kind):
    output = json.loads(json.dumps(ANALYSIS))
    if kind == "few":
        output["questions"] = output["questions"][:2]
    elif kind == "many":
        output["questions"] *= 2
    elif kind == "duplicate_id":
        output["questions"][1]["id"] = "q1"
    elif kind == "duplicate_field":
        output["questions"][1]["field"] = "data"
    elif kind == "overlap":
        output["missing_fields"].append("context")
    else:
        output["questions"][1]["field"] = "score"
    provider(output)
    assert client.post("/api/tasks/analyze", json=DRAFT).status_code == 502


def test_oversized_card_and_publication_in_ai_output_are_rejected(client, provider):
    provider({"card": {"title": "x" * 201}, "warnings": []})
    assert client.post("/api/tasks/build-card", json=DRAFT).status_code == 502
    provider({"card": {"title": "Valid"}, "warnings": [], "confirmed": True})
    assert client.post("/api/tasks/build-card", json=DRAFT).status_code == 502
