"""Task assistants: OpenAI agents when configured, explicit local demo otherwise."""

from app.config import Settings
from app.schemas import AnalyzeRead, AnalyzeRequest, BuildRead, BuildRequest, Card

QUESTIONS = [
    ("data", "Какие данные и материалы уже есть у вас для решения задачи?"),
    ("context", "Что именно происходит сейчас и в чём проблема бизнеса?"),
    ("need", "Какую конкретную потребность или цель должен закрыть продукт?"),
    ("expected_result", "Какой результат вы ожидаете после внедрения решения?"),
    ("success_criteria", "Как вы поймёте, что задача решена успешно? Укажите метрику или процент."),
]


async def analyze(data: AnalyzeRequest, settings: Settings) -> AnalyzeRead:
    if settings.assistant_mode == "openai":
        from app.ai_agents import analyze_draft

        return await analyze_draft(data, settings)
    return AnalyzeRead(
        questions=[
            {"id": f"q{i}", "field": field, "question": question}
            for i, (field, question) in enumerate(QUESTIONS, 1)
        ],
        filled_fields=["topic"] if data.topic else [],
        missing_fields=[field for field, _ in QUESTIONS],
    )


async def build_card(data: BuildRequest, settings: Settings) -> BuildRead:
    if settings.assistant_mode == "openai":
        from app.ai_agents import build_task_card

        return await build_task_card(data, settings)
    values = {answer.field: answer.answer for answer in data.answers if answer.answer}
    values.setdefault("topic", data.topic)
    values.setdefault("context", data.draft_text[:5000])
    values.setdefault("title", data.topic.capitalize())
    card = Card(**values)
    warnings = ["Проверьте название и заполните недостающие поля перед публикацией."]
    if len(data.draft_text) > 5000 and "context" not in {a.field for a in data.answers}:
        warnings.append("В контекст перенесены первые 5000 символов черновика.")
    return BuildRead(card=card, warnings=warnings)
