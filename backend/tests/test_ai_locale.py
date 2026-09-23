from test_ai import client, offline  # noqa: F401

from ai_locale import language, localize, parse_language, system_language_instruction


def test_language_header_localizes_demo_and_resets_between_requests(client):  # noqa: F811
    data = {"draft_text": "We need a website for our bakery.", "topic": "business"}
    for locale, fragment in (("en-US", "What data"), ("kk-KZ", "Сізде қандай")):
        response = client.post("/api/tasks/analyze", json=data, headers={"Accept-Language": locale})
        assert response.status_code == 200
        assert response.json()["questions"][0]["question"].startswith(fragment)
        assert "Деморежим" not in response.json()["warnings"][0]
    response = client.post("/api/tasks/analyze", json=data)
    assert response.json()["questions"][0]["question"].startswith("Какие данные")


def test_localized_build_warning_and_header_fallback(client):  # noqa: F811
    data = {"draft_text": "We need a website for our bakery.", "topic": "business"}
    response = client.post("/api/tasks/build-card", json=data, headers={"Accept-Language": "en"})
    assert response.status_code == 200
    assert all("Поле" not in warning for warning in response.json()["warnings"])
    assert parse_language("fr-FR,en;q=0.8") == "en"
    assert parse_language("kz") == "kk"
    assert parse_language("fr") == "ru"


def test_system_language_preserves_original_evidence():
    token = language.set("kk")
    try:
        assert "Kazakh" in system_language_instruction()
        assert "never translate evidence" in system_language_instruction()
        assert localize("Поле «Контакт» не заполнено: сведений нет в описании.").startswith(
            "«Байланыс»"
        )
    finally:
        language.reset(token)
