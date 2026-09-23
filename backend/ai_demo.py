import re

from schemas_ai import CARD_FIELDS, SCORED_FIELDS, AnswerInput

QUESTION_TEMPLATES = {
    "data": (
        "Какие данные или материалы у вас уже есть и в каком виде? "
        "(например: таблица Excel за 2 месяца, примеры документов)"
    ),
    "expected_result": (
        "Что конкретно команда должна сдать в итоге? (например: веб-форма и отчёт по группам)"
    ),
    "success_criteria": (
        "По какому измеримому признаку вы поймёте, что решение работает? "
        "(например: операция занимает до 1 минуты)"
    ),
    "context": "Как эта задача решается сейчас? (например: вручную в бумажном журнале)",
    "need": "Что именно нужно изменить или улучшить? (например: убрать ручной подсчёт)",
    "users": "Кто будет пользоваться решением? (например: педагоги и администратор)",
    "constraints": (
        "Есть ли ограничения по срокам, технологиям или доступам? (например: 4 недели, только веб)"
    ),
    "contact": "Как команде с вами связаться? (например: email)",
    "interaction_format": "Как вы готовы консультировать команду? (например: созвон раз в неделю)",
}
KEYWORDS = {
    "context": ("сейчас", "вручную", "бумаж", "ведём", "ведем", "используем"),
    "need": ("нужно", "надо", "хотим", "необходимо", "требуется"),
    "data": ("данн", "таблиц", "excel", "эксел", "журнал", "выгруз", "база", "csv"),
    "expected_result": (
        "результат",
        "прототип",
        "дашборд",
        "бот",
        "приложен",
        "сайт",
        "отчёт",
        "отчет",
    ),
    "success_criteria": (),
    "constraints": ("срок", "недел", "месяц", "бюджет", "доступ", "до "),
    "users": (
        "педагог",
        "учител",
        "сотрудник",
        "клиент",
        "родител",
        "ученик",
        "пользоват",
        "менеджер",
    ),
    "contact": ("@", "+7"),
    "interaction_format": ("созвон", "встреч", "раз в", "онлайн", "консультац"),
}
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


def _is_filled(field: str, text: str) -> bool:
    lowered = text.lower()
    if field == "success_criteria":
        return bool(re.search(r"\d|%", text))
    return any(keyword in lowered for keyword in KEYWORDS[field])


def analyze_demo(draft_text: str, topic: str) -> dict:
    filled = [field for field in SCORED_FIELDS if _is_filled(field, draft_text)]
    missing = [field for field in SCORED_FIELDS if field not in filled]
    question_fields = [field for field in QUESTION_TEMPLATES if field in missing]
    if len(question_fields) < 3:
        question_fields.extend(field for field in QUESTION_TEMPLATES if field in filled)
    question_fields = question_fields[:5]
    return {
        "questions": [
            {"id": f"q{index}", "field": field, "question": QUESTION_TEMPLATES[field]}
            for index, field in enumerate(question_fields, 1)
        ],
        "filled_fields": filled,
        "missing_fields": missing,
        "mode": "demo",
    }


def _sentence_for_need(text: str) -> str:
    match = re.search(
        r"[^.!?]*(?:нужно|надо|хотим|необходимо|требуется)[^.!?]*[.!?]?", text, re.IGNORECASE
    )
    return match.group(0).strip() if match else ""


def _title(text: str) -> str:
    first_sentence = re.split(r"[.!?]", text, maxsplit=1)[0].strip()
    return " ".join(first_sentence.split()[:8]).rstrip(".,!? ")


def check_invented(card: dict, draft_text: str, answers: list[AnswerInput]) -> list[str]:
    source = (draft_text + " " + " ".join(answer.answer for answer in answers)).lower()
    warnings = []
    for field, value in card.items():
        if field == "topic" or not value:
            continue
        for item in re.findall(
            r"\d+[.,]?\d*|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|https?://[^\s]+", value
        ):
            if item.lower() not in source:
                warnings.append(
                    f"Поле «{FIELD_LABELS[field]}» содержит «{item}», "
                    "которого нет в вашем описании — проверьте перед публикацией."
                )
    for field in SCORED_FIELDS:
        if not card.get(field):
            warnings.append(f"Поле «{FIELD_LABELS[field]}» не заполнено: сведений нет в описании.")
    return list(dict.fromkeys(warnings))


def build_card_demo(draft_text: str, topic: str, answers: list[AnswerInput]) -> dict:
    card = {field: "" for field in CARD_FIELDS}
    card.update(
        title=_title(draft_text),
        topic=topic.strip(),
        context=draft_text.strip(),
        need=_sentence_for_need(draft_text),
    )
    for answer in answers:
        answer_text = answer.answer.strip()
        if not answer_text or answer.field not in SCORED_FIELDS:
            continue
        value = answer_text[0].upper() + answer_text[1:]
        if value[-1] not in ".!?":
            value += "."
        card[answer.field] = (
            f"{card[answer.field]} {value}".strip() if card[answer.field] else value
        )
    return {"card": card, "warnings": check_invented(card, draft_text, answers), "mode": "demo"}
