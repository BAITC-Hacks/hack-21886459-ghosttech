import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from ai_demo import QUESTION_TEMPLATES, analyze_demo, build_card_demo, check_invented
from schemas_ai import (
    CARD_FIELDS,
    SCORED_FIELDS,
    AnalyzeInput,
    AnalyzeModel,
    AnalyzeOutput,
    BuildCardInput,
    BuildModel,
    BuildOutput,
    Question,
)

load_dotenv(Path(__file__).resolve().parent / ".env")
logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
AI_WARNING = "ИИ временно недоступен, использован демо-режим."


def get_mode() -> str:
    if os.getenv("AI_MODE", "auto").strip().lower() == "demo":
        return "demo"
    return "ai" if os.getenv("OPENAI_API_KEY", "").strip() else "demo"


def _setting(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _prompt(name: str) -> str | None:
    path = PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        logger.warning("AI prompt is unavailable: %s", path)
        return None


ANALYZE_PROMPT = _prompt("analyze.md")
BUILD_CARD_PROMPT = _prompt("build_card.md")


class AIError(RuntimeError):
    pass


def _response_format(system_prompt: str) -> dict:
    def object_schema(properties):
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    text = {"type": "string"}
    card = object_schema({field: text for field in CARD_FIELDS})
    field_name = {"type": "string", "enum": list(SCORED_FIELDS)}
    if system_prompt == ANALYZE_PROMPT:
        schema = object_schema(
            {
                "summary": {"type": "string", "maxLength": 1200},
                "draft_card": card,
                "questions": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": object_schema(
                        {
                            "id": {"type": "string", "minLength": 1, "maxLength": 100},
                            "field": field_name,
                            "question": {"type": "string", "minLength": 1, "maxLength": 300},
                        }
                    ),
                },
                "filled_fields": {"type": "array", "items": field_name},
                "missing_fields": {"type": "array", "items": field_name},
            }
        )
        name = "task_analysis"
    elif system_prompt == BUILD_CARD_PROMPT:
        schema = object_schema({"card": card, "warnings": {"type": "array", "items": text}})
        name = "task_card"
    else:
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }


def call_model(system_prompt: str, payload: dict) -> dict:
    started = time.perf_counter()
    serialized = json.dumps(payload, ensure_ascii=False)
    try:
        from openai import OpenAI

        try:
            with OpenAI(
                api_key=_setting("OPENAI_API_KEY", ""),
                timeout=float(_setting("AI_TIMEOUT_SECONDS", "20")),
                max_retries=0,
            ) as client:
                response = client.chat.completions.create(
                    model=_setting("OPENAI_MODEL", "gpt-5.4-mini"),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": serialized},
                    ],
                    response_format=_response_format(system_prompt),
                    temperature=0.2,
                    timeout=float(_setting("AI_TIMEOUT_SECONDS", "20")),
                )
                content = response.choices[0].message.content or ""
        except Exception as error:
            raise AIError(type(error).__name__) from error
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Ответ модели должен быть JSON-объектом")
        return parsed
    except Exception as error:
        logger.warning("AI call failed: error_type=%s", type(error.__cause__ or error).__name__)
        raise
    finally:
        logger.info(
            "AI call completed: input_length=%d duration_ms=%.0f",
            len(serialized),
            (time.perf_counter() - started) * 1000,
        )


def _model_payload(payload: dict, retry: bool) -> dict:
    if retry:
        payload = dict(payload)
        payload["correction"] = (
            "Предыдущий ответ был некорректным. "
            "Верни только валидный JSON строго по схеме из инструкции."
        )
    return payload


def _validate_analyze(raw: dict) -> AnalyzeModel:
    parsed = AnalyzeModel.model_validate(raw)
    questions = list(parsed.questions)
    candidates = [field for field in QUESTION_TEMPLATES if field not in parsed.filled_fields]
    candidates += [field for field in QUESTION_TEMPLATES if field in parsed.filled_fields]
    for field in candidates:
        if len(questions) >= 3:
            break
        if field not in {question.field for question in questions}:
            questions.append(
                Question(
                    id=f"q{len(questions) + 1}", field=field, question=QUESTION_TEMPLATES[field]
                )
            )
    if len({question.id for question in questions}) != len(questions):
        for index, question in enumerate(questions, 1):
            question.id = f"q{index}"
    parsed.questions = questions
    return parsed


def _normalise_card(raw: dict, data: AnalyzeInput) -> dict:
    source = raw.get("card", {})
    card = {}
    for field in CARD_FIELDS:
        value = source.get(field, "")
        text = str(value).strip() if isinstance(value, (str, int, float, bool)) else ""
        limit = 200 if field == "title" else 500 if field == "contact" else 5000
        card[field] = text[:limit]
    card["topic"] = data.topic
    return card


def _retry_or_demo(function, demo):
    for retry in (False, True):
        try:
            return function(retry)
        except AIError:
            logger.warning("AI provider error; %s", AI_WARNING)
            break
        except (ValueError, TypeError) as error:
            logger.warning(
                "AI response rejected: error_type=%s retry=%s", type(error).__name__, retry
            )
        except Exception as error:
            logger.warning("AI processing failed: error_type=%s", type(error).__name__)
            break
    logger.warning(AI_WARNING)
    return demo()


def analyze_task(data: AnalyzeInput) -> AnalyzeOutput:
    def demo(fallback=True):
        result = analyze_demo(data.draft_text, data.topic)
        result["draft_card"] = build_card_demo(data.draft_text, data.topic, [])["card"]
        result["summary"] = (
            "Показана предварительная проверка по ключевым словам. "
            "Для анализа смысла описания нужен ответ ИИ."
        )
        result["warnings"] = (
            [AI_WARNING] if fallback else ["Деморежим: вопросы шаблонные, анализ ИИ не выполнялся."]
        )
        return AnalyzeOutput(**result)

    if get_mode() == "demo":
        return demo(fallback=False)
    if not ANALYZE_PROMPT:
        logger.warning(AI_WARNING)
        return demo()

    def attempt(retry):
        raw = call_model(ANALYZE_PROMPT, _model_payload(data.model_dump(), retry))
        parsed = _validate_analyze(raw)
        draft = _normalise_card({"card": parsed.draft_card}, data)
        # Scoring must use facts present in the draft, never generated padding.
        source = " ".join(data.draft_text.casefold().split())
        warnings = []
        for field in SCORED_FIELDS:
            value = " ".join(draft[field].casefold().split())
            if value and value not in source:
                draft[field] = ""
                warnings.append("Неподтверждённые сведения исключены из оценки черновика.")
        if parsed.draft_card:
            parsed.filled_fields = [field for field in SCORED_FIELDS if draft[field]]
            parsed.missing_fields = [field for field in SCORED_FIELDS if not draft[field]]
        parsed.draft_card = draft
        return AnalyzeOutput(
            mode="ai", warnings=list(dict.fromkeys(warnings)), **parsed.model_dump()
        )

    return _retry_or_demo(attempt, demo)


def build_card(data: BuildCardInput) -> BuildOutput:
    def demo(fallback=True):
        result = build_card_demo(data.draft_text, data.topic, data.answers)
        if fallback:
            result["warnings"] = list(dict.fromkeys([AI_WARNING, *result["warnings"]]))
        return BuildOutput(**result)

    if get_mode() == "demo":
        return demo(fallback=False)
    if not BUILD_CARD_PROMPT:
        logger.warning(AI_WARNING)
        return demo()

    def attempt(retry):
        raw = call_model(BUILD_CARD_PROMPT, _model_payload(data.model_dump(), retry))
        model = BuildModel.model_validate(raw)
        card = _normalise_card(raw, data)
        warnings = list(
            dict.fromkeys(
                [
                    *model.warnings,
                    *check_invented(card, data.draft_text, data.answers),
                ]
            )
        )
        return BuildOutput(card=card, warnings=warnings, mode="ai")

    return _retry_or_demo(attempt, demo)
