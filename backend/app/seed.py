import json
from datetime import date, datetime, timedelta, timezone

from app.config import ROOT_DIR
from app.models import Participant, Progress, Proposal, Task, Team
from app.schemas import Card
from app.scoring import score_card


def seed_database(db):
    """Add missing demo records. Never reset edited data or decisions."""
    counts = {"tasks": 0, "teams": 0, "proposals": 0, "participants": 0, "progress": 0}

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
    seed_demo_world(db, counts)
    return counts


def seed_demo_world(db, counts):
    world = json.loads((ROOT_DIR / "sample_data/demo_world.json").read_text())
    now = datetime.now(timezone.utc)

    def created(item):
        return now - timedelta(days=item["age_days"])

    def add(model, key, values):
        if db.get(model, values["id"]):
            return False
        db.add(model(**values))
        counts[key] += 1
        return True

    for item in world["teams"]:
        add(Team, "teams", item)
    db.flush()
    for item in world["participants"]:
        add(Participant, "participants", item)
    db.flush()
    for item in world["tasks"]:
        card = Card(**item["card"])
        score = score_card(card)
        add(
            Task,
            "tasks",
            {
                "id": item["id"],
                **card.model_dump(),
                "owner_id": item["owner_id"],
                "is_demo": True,
                "work_tags": item["work_tags"],
                "confirmed": True,
                "score": score.score,
                "level": score.level,
                "created_at": created(item),
                "updated_at": created(item),
            },
        )
    db.flush()
    added_proposals = set()
    for item in world["proposals"]:
        values = {
            key: value for key, value in item.items() if key not in {"age_days", "deadline_days"}
        }
        values.update(
            created_at=created(item), deadline=now.date() + timedelta(days=item["deadline_days"])
        )
        if add(Proposal, "proposals", values):
            added_proposals.add(item["id"])
    db.flush()
    for item in world["progress"]:
        # Only initialize new proposals; never advance a user's existing project on re-seed.
        if item["proposal_id"] in added_proposals:
            values = {key: value for key, value in item.items() if key != "age_days"}
            add(Progress, "progress", {**values, "created_at": created(item)})
    db.flush()
