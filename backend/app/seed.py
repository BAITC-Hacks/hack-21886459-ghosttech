import json
from datetime import date, datetime

from app.config import ROOT_DIR
from app.models import Proposal, Task, Team
from app.schemas import Card
from app.scoring import score_card


def seed_database(db):
    """Add missing demo records. Never reset edited data or decisions."""
    counts = {"tasks": 0, "teams": 0, "proposals": 0}

    def read(name):
        return json.loads((ROOT_DIR / "sample_data" / f"{name}.json").read_text())

    for item in read("teams"):
        if db.get(Team, item["id"]):
            continue
        counts["teams"] += 1
        db.add(
            Team(
                id=item["id"],
                name=item["name"],
                interests=item["interests"],
                skills=item["skills"],
                tech=item["tech"],
                base_points=item["points"],
            )
        )
    db.flush()
    for item in read("cards"):
        if db.get(Task, item["id"]):
            continue
        card = Card(**item["card"])
        score = score_card(card)
        counts["tasks"] += 1
        db.add(
            Task(
                id=item["id"],
                **card.model_dump(),
                confirmed=True,
                score=score.score,
                level=score.level,
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
            )
        )
    db.flush()
    for item in read("proposals"):
        if db.get(Proposal, item["id"]):
            continue
        counts["proposals"] += 1
        db.add(Proposal(**{**item, "deadline": date.fromisoformat(item["deadline"])}))
    db.flush()
    return counts
