"""Persist the per-account budget before any assistant provider call."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


def reserve_ai_request(db: Session, participant_id: str, daily_limit: int):
    day = datetime.now(timezone.utc).date().isoformat()
    db.execute(
        text(
            "INSERT INTO ai_usage (participant_id, day, requests) "
            "VALUES (:participant_id, :day, 0) "
            "ON CONFLICT (participant_id, day) DO NOTHING"
        ),
        {"participant_id": participant_id, "day": day},
    )
    result = db.execute(
        text(
            "UPDATE ai_usage SET requests = requests + 1 "
            "WHERE participant_id = :participant_id AND day = :day AND requests < :daily_limit"
        ),
        {"participant_id": participant_id, "day": day, "daily_limit": daily_limit},
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(429, "Дневной лимит обращений к ИИ исчерпан")
    db.commit()
