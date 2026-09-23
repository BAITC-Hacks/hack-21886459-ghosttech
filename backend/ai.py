import json
import logging
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

from ai_demo import QUESTION_TEMPLATES, analyze_demo, build_card_demo, check_invented as demo_check_invented
from schemas_ai import (
    CARD_FIELDS,
    SCORED_FIELDS,
    AnalyzeInput,
    AnalyzeModel,
    AnalyzeOutput,
    BuildCardInput,
    BuildModel,
    BuildOutput,
)

load_dotenv(Path(__file__).resolve().parent / ".env")
logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
AI_WARNING = "ИИ временно недоступен, использован демо-режим."
FIELD_LABELS = {
    "context": "Контекст",
    "need": "Потребность",
    "data": "Данные и материалы",
    "expected_result": "Ожидаемый результат",
    "success_criteria": "Критерии успеха",
    "constraints": "Ограничения",
    "users": "Пользователи",
    "contact": "Контакт",
    "interaction_format": "Формат взаимодействия",
    "title": "Название",
}


def get_mode() -> str:
    if os.getenv("AI_MODE", "auto").strip().lower() == "demo":
        return "demo"
    return "ai" if os.getenv("OPENAI_API_KEY", "").strip() else "demo"


def _setting(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _prompt(name: str) -> str | None:
    path = PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("AI prompt is unavailable: %s", path)
        return None

ANALYZE_PROMPT = _prompt("analyze.md")
BUILD_CARD_PROMPT = _prompt("build_card.md")


class AIError(RuntimeError):
    pass


def call_model(system_prompt: str, payload: dict) -> dict:
    started = time.perf_counter()
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=_setting("OPENAI_API_KEY", ""),
            timeout=float(_setting("AI_TIMEOUT_SECONDS", "20")),
        )
        response = client.chat.completions.create(
            model=_setting("OPENAI_MODEL", "gpt-5.4-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=float(_setting("AI_TIMEOUT_SECONDS", "20")),
        )
        content = response.choices[0].message.content or ""
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Ответ модели должен быть JSON-объектом")
        return parsed
    except Exception as error:
        raise AIError(type(error).__name__) from error
    finally:
        logger.info("AI call completed: input_length=%d duration_ms=%.0f", len(json.dumps(payload, ensure_ascii=False)), (time.perf_counter() - started) * 1000)


def _model_payload(payload: dict, retry: bool) -> dict:
    if retry:
        payload = dict(payload)
        payload["correction"] = "Предыдущий ответ был некорректным. Верни только валидный JSON строго по схеме из инструкции."
    return payload


def _validate_analyze(raw: dict) -> AnalyzeModel:
    parsed = AnalyzeModel.model_validate(raw)
    questions = []
    for index, question in enumerate(parsed.questions, 1):
        question.id = f"q{index}" if any(item.id == question.id for item in questions) else question.id
        questions.append(question)
    parsed.questions = questions[:5]
    if len(parsed.questions) < 3:
        for field in QUESTION_TEMPLATES:
            if field not in {question.field for question in parsed.questions}:
                parsed.questions.append({"id": f"q{len(parsed.questions) + 1}", "field": field, "question": QUESTION_TEMPLATES[field]})
            if len(parsed.questions) == 3:
                break
    parsed.questions = parsed.questions[:5]
    return parsed


def _normalise_card(raw: dict, data: BuildCardInput) -> dict:
    source = raw.get("card", {}) if isinstance(raw, dict) else {}
    card = {}
    for field in CARD_FIELDS:
        value = source.get(field, "") if isinstance(source, dict) else ""
        card[field] = str(value).strip() if isinstance(value, (str, int, float, bool)) else ""
    card["topic"] = data.topic.strip()
    return card


def _invented_warnings(card: dict, draft_text: str, answers) -> list[str]:
    source = (draft_text + " " + " ".join(answer.answer for answer in answers)).lower()
    warnings = []
    for field, value in card.items():
        if field == "topic" or not value:
            continue
        found = re.findall(r"\d+[.,]?\d*|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|https?://[^\s]+", value)
        for item in found:
            if item.lower() not in source:
                warnings.append(f"Поле «{FIELD_LABELS[field]}» содержит «{item}», которого нет в вашем описании — проверьте перед публикацией.")
    for field in SCORED_FIELDS:
        if not card.get(field):
            warnings.append(f"Поле «{FIELD_LABELS[field]}» не заполнено: сведений нет в описании.")
    return list(dict.fromkeys(warnings))


def check_invented(card: dict, draft_text: str, answers) -> list[str]:
    return demo_check_invented(card, draft_text, answers)


def _retry_or_demo(function, demo):
    try:
        return function(False)
    except (AIError, ValueError, TypeError, json.JSONDecodeError):
        try:
            return function(True)
        except Exception:
            return demo()


def analyze_task(data: AnalyzeInput) -> AnalyzeOutput:
    if get_mode() == "demo" or not ANALYZE_PROMPT:
        return AnalyzeOutput(**analyze_demo(data.draft_text, data.topic))

    def attempt(retry):
        raw = call_model(ANALYZE_PROMPT, _model_payload(data.model_dump(), retry))
        return AnalyzeOutput(mode="ai", **_validate_analyze(raw).model_dump())

    return _retry_or_demo(attempt, lambda: AnalyzeOutput(**analyze_demo(data.draft_text, data.topic)))


def build_card(data: BuildCardInput) -> BuildOutput:
    def demo():
        result = build_card_demo(data.draft_text, data.topic, data.answers)
        result["warnings"] = list(dict.fromkeys([AI_WARNING, *result["warnings"], *_invented_warnings(result["card"], data.draft_text, data.answers)]))
        return BuildOutput(**result)

    if get_mode() == "demo" or not BUILD_CARD_PROMPT:
        result = build_card_demo(data.draft_text, data.topic, data.answers)
        warnings = [] if get_mode() == "demo" and BUILD_CARD_PROMPT else [AI_WARNING]
        result["warnings"] = list(dict.fromkeys([*warnings, *result["warnings"], *_invented_warnings(result["card"], data.draft_text, data.answers)]))
        return BuildOutput(**result)

    def attempt(retry):
        raw = call_model(BUILD_CARD_PROMPT, _model_payload(data.model_dump(), retry))
        model = BuildModel.model_validate(raw)
        card = _normalise_card(raw, data)
        warnings = list(dict.fromkeys([*model.warnings, *_invented_warnings(card, data.draft_text, data.answers)]))
        return BuildOutput(card=card, warnings=warnings, mode="ai")

    try:
        return _retry_or_demo(attempt, demo)
    except Exception:
        return demo()
