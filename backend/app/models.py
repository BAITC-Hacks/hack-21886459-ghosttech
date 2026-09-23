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
    contact: Mapped[str] = mapped_column(String(500), default="")
    is_demo: Mapped[bool] = mapped_column(default=False)
    members: Mapped[list["Participant"]] = relationship(back_populates="team", lazy="selectin")


class Participant(Base):
    """Public profiles; only non-demo profiles may be linked to accounts."""

    __tablename__ = "participants"
    __table_args__ = (
        CheckConstraint("role IN ('business', 'student')", name="ck_participant_role"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(16))
    organization: Mapped[str] = mapped_column(String(150), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_demo: Mapped[bool] = mapped_column(default=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), index=True)
    team: Mapped["Team | None"] = relationship(back_populates="members")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id"), unique=True, index=True
    )
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    participant: Mapped[Participant] = relationship(lazy="selectin")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    account: Mapped[Account] = relationship(lazy="selectin")


class AiUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (CheckConstraint("requests >= 0", name="ck_ai_usage_requests"),)

    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    requests: Mapped[int] = mapped_column(default=0)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_task_score"),
        CheckConstraint("level IN ('draft', 'working', 'ready', 'priority')", name="ck_task_level"),
        Index("ix_tasks_catalog", "confirmed", "topic", "level", "score"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("participants.id"), index=True)
    owner: Mapped["Participant | None"] = relationship(lazy="selectin")
    is_demo: Mapped[bool] = mapped_column(default=False)
    work_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
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
