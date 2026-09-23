import json
import re

from app.config import ROOT_DIR
from app.schemas import Card, Score

FIELD_CONFIG = {
    "context": (10, 40, 10),
    "need": (10, 40, 10),
    "data": (20, 30, 20),
    "expected_result": (15, 30, 15),
    "success_criteria": (15, 1, 10),
    "constraints": (10, 20, 10),
    "users": (10, 20, 10),
    "contact": (5, 1, 0),
    "interaction_format": (5, 1, 0),
}
HINTS = json.loads((ROOT_DIR / "prompts/field_hints.json").read_text())


def score_card(card: Card) -> Score:
    breakdown, missing = [], []
    for field, (maximum, full, half) in FIELD_CONFIG.items():
        value = getattr(card, field).strip()
        if not value:
            earned = 0
        elif field == "success_criteria":
            earned = maximum if re.search(r"[0-9%]", value) else 10
        elif len(value) >= full:
            earned = maximum
        elif len(value) >= half:
            earned = maximum // 2
        else:
            earned = 0
        breakdown.append(
            {
                "field": field,
                "label": HINTS[field]["label"],
                "max": maximum,
                "earned": earned,
                "reason": (
                    "Поле заполнено"
                    if earned == maximum
                    else HINTS[field]["hint_empty" if not earned else "hint_partial"]
                ),
            }
        )
        if earned < maximum:
            missing.append(
                {
                    "field": field,
                    "hint": HINTS[field]["hint_empty" if not earned else "hint_partial"],
                    "potential_points": maximum - earned,
                }
            )
    score = sum(row["earned"] for row in breakdown)
    level = (
        "priority"
        if score >= 90
        else "ready"
        if score >= 70
        else "working"
        if score >= 40
        else "draft"
    )
    return Score(score=score, level=level, breakdown=breakdown, missing=missing)
