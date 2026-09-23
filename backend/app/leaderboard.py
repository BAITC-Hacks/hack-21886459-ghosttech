"""Public rankings use published work and dated, business-confirmed milestones."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import case, func, select

from app.database import Db
from app.models import Participant, Progress, Proposal, Task, Team
from app.routes import STAGE_POINTS, find, task_summaries, team_read
from app.schemas import BusinessProfileRead, LeaderboardRead, TeamProfileRead

router = APIRouter(tags=["profiles"])
Period = Literal["month", "all"]


def utcnow():
    return datetime.now(timezone.utc)


def period_filter(column, start, now):
    conditions = [column <= now]
    if start is not None:
        conditions.append(column >= start)
    return conditions


def accepted_task():
    return (
        select(Proposal.id)
        .where(Proposal.task_id == Task.id, Proposal.status == "accepted")
        .exists()
    )


@router.get("/leaderboard", response_model=LeaderboardRead)
def leaderboard(db: Db, period: Period = "month", limit: int = Query(10, ge=1, le=50)):
    now = utcnow()
    start = (
        now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) if period == "month" else None
    )
    published = (
        select(
            Task.owner_id.label("owner_id"),
            func.sum(Task.score).label("points"),
            func.count(Task.id).label("count"),
            func.avg(Task.score).label("average"),
        )
        .where(Task.confirmed.is_(True), *period_filter(Task.created_at, start, now))
        .group_by(Task.owner_id)
        .subquery()
    )
    open_tasks = (
        select(Task.owner_id.label("owner_id"), func.count(Task.id).label("count"))
        .where(Task.confirmed.is_(True), ~accepted_task())
        .group_by(Task.owner_id)
        .subquery()
    )
    progress_query = (
        select(
            func.sum(Progress.points).label("points"),
            func.count(Progress.id).label("stages"),
            func.count(func.distinct(case((Progress.stage == "final", Task.id)))).label(
                "completed"
            ),
        )
        .select_from(Progress)
        .join(Proposal, Proposal.id == Progress.proposal_id)
        .join(Task, Task.id == Proposal.task_id)
        .where(
            Proposal.status == "accepted",
            Task.confirmed.is_(True),
            *period_filter(Progress.created_at, start, now),
        )
    )
    business_progress = (
        progress_query.add_columns(Task.owner_id.label("owner_id"))
        .group_by(Task.owner_id)
        .subquery()
    )
    points = func.coalesce(published.c.points, 0) + func.coalesce(business_progress.c.points, 0)
    business_query = (
        select(
            Participant,
            points.label("points"),
            func.coalesce(published.c.count, 0).label("published_tasks"),
            func.coalesce(published.c.average, 0).label("average_readiness"),
            func.coalesce(business_progress.c.completed, 0).label("completed_tasks"),
            func.coalesce(open_tasks.c.count, 0).label("open_tasks"),
        )
        .outerjoin(published, published.c.owner_id == Participant.id)
        .outerjoin(business_progress, business_progress.c.owner_id == Participant.id)
        .outerjoin(open_tasks, open_tasks.c.owner_id == Participant.id)
        .where(
            Participant.role == "business",
            (published.c.count > 0) | (business_progress.c.stages > 0),
        )
        .order_by(
            points.desc(), func.coalesce(business_progress.c.completed, 0).desc(), Participant.id
        )
        .limit(limit)
    )
    businesses = []
    for rank, row in enumerate(db.execute(business_query), 1):
        businesses.append(
            {
                "rank": rank,
                "profile": row.Participant,
                "points": row.points,
                "published_tasks": row.published_tasks,
                "average_readiness": round(float(row.average_readiness), 1),
                "completed_tasks": row.completed_tasks,
                "open_tasks": row.open_tasks,
            }
        )
    team_progress = (
        progress_query.add_columns(Proposal.team_id.label("team_id"))
        .group_by(Proposal.team_id)
        .subquery()
    )
    team_points = func.coalesce(team_progress.c.points, 0)
    if period == "all":
        team_points = team_points + Team.base_points
    team_query = (
        select(
            Team,
            team_points.label("points"),
            func.coalesce(team_progress.c.completed, 0).label("completed"),
            func.coalesce(team_progress.c.stages, 0).label("stages"),
        )
        .outerjoin(team_progress, team_progress.c.team_id == Team.id)
        .where(team_points > 0)
        .order_by(team_points.desc(), func.coalesce(team_progress.c.completed, 0).desc(), Team.id)
        .limit(limit)
    )
    teams = [
        {
            "rank": rank,
            "team": team_read(db, row.Team),
            "points": row.points,
            "completed_tasks": row.completed,
            "confirmed_stages": row.stages,
        }
        for rank, row in enumerate(db.execute(team_query), 1)
    ]
    return {
        "period": period,
        "starts_at": start,
        "as_of": now,
        "businesses": businesses,
        "teams": teams,
    }


def public_tasks(db, query):
    tasks = task_summaries(db, query)
    ids = [task["id"] for task in tasks]
    assigned = (
        set(
            db.scalars(
                select(Proposal.task_id).where(
                    Proposal.task_id.in_(ids), Proposal.status == "accepted"
                )
            )
        )
        if ids
        else set()
    )
    return [{**task, "open_for_proposals": task["id"] not in assigned} for task in tasks]


@router.get("/profiles/businesses/{business_id}", response_model=BusinessProfileRead)
def business_profile(
    db: Db, business_id: str, offset: int = Query(0, ge=0), limit: int = Query(12, ge=1, le=100)
):
    profile = find(db, Participant, business_id)
    if profile.role != "business":
        raise HTTPException(404, "Профиль бизнеса не найден")
    conditions = (Task.confirmed.is_(True), Task.owner_id == profile.id)
    query = select(Task).where(*conditions).order_by(accepted_task(), Task.score.desc(), Task.id)
    contacts = db.scalars(
        select(Task.contact).where(*conditions, Task.contact != "").distinct()
    ).all()
    return {
        "profile": profile,
        "contacts": sorted({value.strip() for value in contacts if value.strip()}),
        "tasks": public_tasks(db, query.offset(offset).limit(limit)),
        "total_tasks": db.scalar(select(func.count(Task.id)).where(*conditions)),
        "open_tasks": db.scalar(select(func.count(Task.id)).where(*conditions, ~accepted_task())),
    }


@router.get("/profiles/teams/{team_id}", response_model=TeamProfileRead)
def team_profile(
    db: Db, team_id: str, offset: int = Query(0, ge=0), limit: int = Query(12, ge=1, le=100)
):
    team = find(db, Team, team_id)
    conditions = (
        Proposal.team_id == team.id,
        Proposal.status == "accepted",
        Task.confirmed.is_(True),
    )
    projects = db.scalars(
        select(Proposal)
        .join(Task)
        .where(*conditions)
        .order_by(Proposal.created_at.desc(), Proposal.id)
        .offset(offset)
        .limit(limit)
    ).all()
    tasks = {
        task["id"]: task
        for task in public_tasks(db, select(Task).where(Task.id.in_([p.task_id for p in projects])))
    }
    return {
        "team": team_read(db, team),
        "total_projects": db.scalar(select(func.count(Proposal.id)).join(Task).where(*conditions)),
        "projects": [
            {
                "task": tasks[p.task_id],
                "stages_done": sorted((row.stage for row in p.progress), key=STAGE_POINTS.get),
                "prototype_url": p.prototype_url,
            }
            for p in projects
        ],
    }
