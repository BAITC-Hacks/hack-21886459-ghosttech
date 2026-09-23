from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id():
    return uuid4().hex


def utcnow():
    return datetime.now(timezone.utc)


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (CheckConstraint("base_points >= 0", name="ck_team_points"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    tech: Mapped[list[str]] = mapped_column(JSON, default=list)
    base_points: Mapped[int] = mapped_column(default=0)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_task_score"),
        CheckConstraint("level IN ('draft', 'working', 'ready', 'priority')", name="ck_task_level"),
        Index("ix_tasks_catalog", "confirmed", "topic", "level", "score"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(100))
    context: Mapped[str] = mapped_column(Text, default="")
    need: Mapped[str] = mapped_column(Text, default="")
    users: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[str] = mapped_column(Text, default="")
    constraints: Mapped[str] = mapped_column(Text, default="")
    expected_result: Mapped[str] = mapped_column(Text, default="")
    success_criteria: Mapped[str] = mapped_column(Text, default="")
    contact: Mapped[str] = mapped_column(String(500), default="")
    interaction_format: Mapped[str] = mapped_column(Text, default="")
    confirmed: Mapped[bool] = mapped_column(default=False)
    score: Mapped[int] = mapped_column(default=0)
    level: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (
        UniqueConstraint("task_id", "team_id", name="uq_task_team"),
        CheckConstraint("status IN ('pending', 'accepted', 'rejected')", name="ck_proposal_status"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    idea: Mapped[str] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(Text)
    deadline: Mapped[date]
    prototype_url: Mapped[str] = mapped_column(String(2048), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    progress: Mapped[list["Progress"]] = relationship(back_populates="proposal", lazy="selectin")


class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (
        UniqueConstraint("proposal_id", "stage", name="uq_proposal_stage"),
        CheckConstraint("stage IN ('prototype', 'testing', 'final')", name="ck_progress_stage"),
        CheckConstraint(
            "(stage = 'prototype' AND points = 10) OR (stage = 'testing' AND points = 20) "
            "OR (stage = 'final' AND points = 30)",
            name="ck_stage_points",
        ),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    stage: Mapped[str] = mapped_column(String(16))
    points: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    proposal: Mapped[Proposal] = relationship(back_populates="progress")
