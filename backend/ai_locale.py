"""Per-request language, including deterministic offline assistant messages."""

import re
from contextvars import ContextVar

language = ContextVar("assistant_language", default="ru")

QUESTIONS = {
    "en": {
        "data": "What data or materials do you already have, and in what format?",
        "expected_result": "What exactly should the team deliver at the end?",
        "success_criteria": "What measurable result will show that the solution works?",
        "context": "How is this task handled today?",
        "need": "What exactly needs to change or improve?",
        "users": "Who will use the solution?",
        "constraints": "Are there limits on time, technology, budget, or access?",
        "contact": "How can the team contact you?",
        "interaction_format": "How will you provide feedback to the team?",
    },
    "kk": {
        "data": "Сізде қандай деректер немесе материалдар бар және олар қандай форматта?",
        "expected_result": "Команда жұмыстың соңында нақты не тапсыруы керек?",
        "success_criteria": "Шешімнің жұмыс істейтінін қандай өлшенетін нәтиже көрсетеді?",
        "context": "Бұл тапсырма қазір қалай орындалады?",
        "need": "Нақты нені өзгерту немесе жақсарту керек?",
        "users": "Шешімді кім қолданады?",
        "constraints": "Мерзім, технология, бюджет немесе қолжетімділік бойынша шектеулер бар ма?",
        "contact": "Команда сізбен қалай байланыса алады?",
        "interaction_format": "Командаға кері байланысты қалай бересіз?",
    },
}

MESSAGES = {
    "ИИ временно недоступен, использован демо-режим.": (
        "AI is temporarily unavailable; demo mode was used.",
        "ЖИ уақытша қолжетімсіз, демо режимі қолданылды.",
    ),
    "Деморежим: вопросы шаблонные, анализ ИИ не выполнялся.": (
        "Demo mode: template questions; no AI analysis was performed.",
        "Демо режимі: сұрақтар үлгі бойынша жасалды, ЖИ талдауы орындалмады.",
    ),
    "Показана предварительная проверка по ключевым словам. Для анализа смысла описания нужен ответ ИИ.": (  # noqa: E501
        "This is a preliminary keyword check. AI is required to analyze the meaning of the description.",  # noqa: E501
        "Кілт сөздер бойынша алдын ала тексеру көрсетілген. Сипаттаманың мағынасын талдау үшін ЖИ жауабы қажет.",  # noqa: E501
    ),
    "Неподтверждённые сведения исключены из оценки черновика.": (
        "Unconfirmed details were excluded from the draft score.",
        "Расталмаған мәліметтер жоба бағалауынан алынып тасталды.",
    ),
}

LABELS = {
    "Контекст": ("Context", "Мәнмәтін"),
    "Потребность": ("Need", "Қажеттілік"),
    "Данные и материалы": ("Data and materials", "Деректер мен материалдар"),
    "Ожидаемый результат": ("Expected result", "Күтілетін нәтиже"),
    "Критерии успеха": ("Success criteria", "Табыс критерийлері"),
    "Ограничения": ("Constraints", "Шектеулер"),
    "Пользователи": ("Users", "Пайдаланушылар"),
    "Контакт": ("Contact", "Байланыс"),
    "Формат взаимодействия": ("Interaction format", "Өзара әрекеттесу форматы"),
    "Название": ("Title", "Атауы"),
}


def parse_language(value: str) -> str:
    for part in value.lower().split(","):
        code = part.strip().split(";", 1)[0].split("-", 1)[0]
        if code == "kz":
            code = "kk"
        if code in ("ru", "kk", "en"):
            return code
    return "ru"


def localize(message: str) -> str:
    lang = language.get()
    if lang == "ru":
        return message
    index = 0 if lang == "en" else 1
    if message in MESSAGES:
        return MESSAGES[message][index]
    missing = re.fullmatch(r"Поле «(.+)» не заполнено: сведений нет в описании\.", message)
    if missing:
        field = LABELS.get(missing[1], (missing[1], missing[1]))[index]
        return (
            f"The '{field}' field is empty: the description contains no information."
            if lang == "en"
            else f"«{field}» өрісі толтырылмаған: сипаттамада мәлімет жоқ."
        )
    invented = re.fullmatch(
        r"Поле «(.+)» содержит «(.+)», которого нет в вашем описании — проверьте перед публикацией\.",  # noqa: E501
        message,
    )
    if invented:
        field = LABELS.get(invented[1], (invented[1], invented[1]))[index]
        return (
            f"The '{field}' field includes '{invented[2]}', which is absent from your description. Check before publishing."  # noqa: E501
            if lang == "en"
            else f"«{field}» өрісіндегі «{invented[2]}» сипаттамаңызда жоқ. Жарияламас бұрын тексеріңіз."  # noqa: E501
        )
    return message


def system_language_instruction() -> str:
    lang = language.get()
    if lang == "ru":
        return ""
    name = "English" if lang == "en" else "Kazakh (қазақ тілі)"
    return (
        f"\nResponse language override: write summary, questions, title, generated card prose "
        f"and warnings in {name}, regardless of the input language. Keep JSON keys unchanged. "
        "For analysis draft_card evidence fields, still copy exact original source excerpts; "
        "never translate evidence. Preserve the original topic, names, contacts, URLs and numbers."
    )
