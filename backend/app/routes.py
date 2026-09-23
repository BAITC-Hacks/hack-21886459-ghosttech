from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app import assistant
from app.database import Db
from app.models import Participant, Progress, Proposal, Task, Team
from app.schemas import (
    AnalyzeRead,
    AnalyzeRequest,
    BuildRead,
    BuildRequest,
    Card,
    CardRequest,
    Decision,
    Level,
    ParticipantRead,
    ProgressCreate,
    ProgressRead,
    ProposalCreate,
    ProposalRead,
    Score,
    TaskCreate,
    TaskRead,
    TaskSummary,
    TaskUpdate,
    TeamCreate,
    TeamRead,
    TopicRead,
)
from app.scoring import score_card

router = APIRouter()
STAGE_POINTS = {"prototype": 10, "testing": 20, "final": 30}


def find(db, model, identifier):
    item = db.get(model, identifier)
    if not item:
        raise HTTPException(404, "Запись не найдена")
    return item


def team_points(db, team: Team):
    earned = db.scalar(
        select(func.coalesce(func.sum(Progress.points), 0))
        .join(Proposal)
        .where(Proposal.team_id == team.id)
    )
    return team.base_points + earned


def team_read(db, team: Team):
    return {
        "id": team.id,
        "name": team.name,
        "interests": team.interests,
        "skills": team.skills,
        "tech": team.tech,
        "points": team_points(db, team),
        "members": team.members,
        "is_demo": team.is_demo,
    }


def proposal_read(proposal: Proposal):
    return {
        "id": proposal.id,
        "task_id": proposal.task_id,
        "team_id": proposal.team_id,
        "idea": proposal.idea,
        "plan": proposal.plan,
        "deadline": proposal.deadline,
        "prototype_url": proposal.prototype_url,
        "status": proposal.status,
        "created_at": proposal.created_at,
        "stages_done": sorted((row.stage for row in proposal.progress), key=STAGE_POINTS.get),
    }


def task_read(db, task: Task):
    card = Card(**{field: getattr(task, field) for field in Card.model_fields})
    proposals = select(Proposal).where(Proposal.task_id == task.id).order_by(Proposal.created_at)
    return {
        "id": task.id,
        "card": card,
        "confirmed": task.confirmed,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "owner": task.owner,
        "is_demo": task.is_demo,
        "work_tags": task.work_tags,
        **score_card(card).model_dump(),
        "proposals": [proposal_read(p) for p in db.scalars(proposals).all()],
    }


def task_summaries(db, query):
    count = select(func.count(Proposal.id)).where(Proposal.task_id == Task.id).scalar_subquery()
    return [
        {
            "id": task.id,
            "title": task.title,
            "topic": task.topic,
            "need": task.need,
            "confirmed": task.confirmed,
            "score": task.score,
            "level": task.level,
            "created_at": task.created_at,
            "proposals_count": total,
            "owner": task.owner,
            "is_demo": task.is_demo,
            "work_tags": task.work_tags,
        }
        for task, total in db.execute(query.add_columns(count))
    ]


@router.post("/tasks/analyze", response_model=AnalyzeRead, tags=["assistant"])
async def analyze(data: AnalyzeRequest, request: Request):
    return await assistant.analyze(data, request.app.state.settings)


@router.post("/tasks/build-card", response_model=BuildRead, tags=["assistant"])
async def build_card(data: BuildRequest, request: Request):
    return await assistant.build_card(data, request.app.state.settings)


@router.post("/tasks/score", response_model=Score, tags=["assistant"])
def score(data: CardRequest):
    return score_card(data.card)


@router.get("/tasks", response_model=list[TaskSummary], tags=["tasks"])
def tasks(
    db: Db,
    topic: str = Query("", max_length=100),
    level: Level | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    include_drafts: bool = False,
    owner_id: str = Query("", max_length=32),
    search: str = Query("", max_length=200),
    work_type: str = Query("", max_length=100),
    proposals: Literal["any", "none", "has"] = "any",
    sort: Literal["score_desc", "score_asc", "newest", "oldest", "proposals_desc"] = "score_desc",
):
    query = select(Task)
    if not include_drafts:
        query = query.where(Task.confirmed.is_(True))
    if topic:
        query = query.where(Task.topic == topic)
    if level:
        query = query.where(Task.level == level)
    if owner_id:
        query = query.where(Task.owner_id == owner_id)
    if search.strip():
        query = query.where(
            or_(
                Task.title.icontains(search.strip(), autoescape=True),
                Task.need.icontains(search.strip(), autoescape=True),
            )
        )
    if work_type:
        if db.get_bind().dialect.name == "sqlite":
            tags = func.json_each(Task.work_tags).table_valued("value")
        else:
            tags = (
                func.json_array_elements_text(Task.work_tags).table_valued("value").render_derived()
            )
        query = query.where(
            select(1).select_from(tags).where(tags.c.value == work_type).correlate(Task).exists()
        )
    count = select(func.count(Proposal.id)).where(Proposal.task_id == Task.id).scalar_subquery()
    if proposals == "none":
        query = query.where(count == 0)
    elif proposals == "has":
        query = query.where(count > 0)
    ordering = {
        "score_desc": (Task.score.desc(), Task.created_at.desc()),
        "score_asc": (Task.score.asc(), Task.created_at.desc()),
        "newest": (Task.created_at.desc(), Task.score.desc()),
        "oldest": (Task.created_at.asc(), Task.score.desc()),
        "proposals_desc": (count.desc(), Task.score.desc(), Task.created_at.desc()),
    }
    return task_summaries(db, query.order_by(*ordering[sort], Task.id).offset(offset).limit(limit))


@router.post("/tasks", response_model=TaskRead, status_code=201, tags=["tasks"])
def create_task(data: TaskCreate, db: Db):
    owner = find(db, Participant, data.owner_id) if data.owner_id else None
    if owner and owner.role != "business":
        raise HTTPException(422, "Автором задачи может быть только предприниматель")
    score = score_card(data.card)
    task = Task(
        **data.card.model_dump(),
        confirmed=data.confirmed,
        score=score.score,
        level=score.level,
        owner_id=data.owner_id,
        is_demo=bool(owner and owner.is_demo),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task_read(db, task)


@router.get("/tasks/{task_id}", response_model=TaskRead, tags=["tasks"])
def get_task(task_id: str, db: Db):
    task = find(db, Task, task_id)
    return task_read(db, task)


@router.patch("/tasks/{task_id}", response_model=TaskRead, tags=["tasks"])
def update_task(task_id: str, data: TaskUpdate, db: Db):
    task = find(db, Task, task_id)
    if data.card is not None:
        for key, value in data.card.model_dump().items():
            setattr(task, key, value)
        scored = score_card(data.card)
        task.score, task.level = scored.score, scored.level
        task.confirmed = False
    if data.confirmed is not None:
        task.confirmed = data.confirmed
    if task.confirmed and (not task.title or not task.topic):
        raise HTTPException(422, "Для публикации заполните название и тему")
    db.commit()
    db.refresh(task)
    return task_read(db, task)


@router.get("/topics", response_model=list[TopicRead], tags=["tasks"])
def topics(db: Db):
    return [
        {"topic": topic, "tasks_count": count}
        for topic, count in db.execute(
            select(Task.topic, func.count(Task.id))
            .where(Task.confirmed.is_(True))
            .group_by(Task.topic)
            .order_by(Task.topic)
        )
    ]


@router.get("/participants", response_model=list[ParticipantRead], tags=["participants"])
def participants(
    db: Db,
    role: Literal["business", "student"] | None = None,
    team_id: str = Query("", max_length=32),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    query = select(Participant)
    if role:
        query = query.where(Participant.role == role)
    if team_id:
        query = query.where(Participant.team_id == team_id)
    return db.scalars(
        query.order_by(Participant.name, Participant.id).offset(offset).limit(limit)
    ).all()


@router.get("/teams", response_model=list[TeamRead], tags=["teams"])
def teams(db: Db, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return [
        team_read(db, team)
        for team in db.scalars(
            select(Team).order_by(Team.name, Team.id).offset(offset).limit(limit)
        )
    ]


@router.post("/teams", response_model=TeamRead, status_code=201, tags=["teams"])
def create_team(data: TeamCreate, db: Db):
    team = Team(**data.model_dump())
    db.add(team)
    db.commit()
    return team_read(db, team)


@router.patch("/teams/{team_id}", response_model=TeamRead, tags=["teams"])
def update_team(team_id: str, data: TeamCreate, db: Db):
    team = find(db, Team, team_id)
    for key, value in data.model_dump().items():
        setattr(team, key, value)
    db.commit()
    return team_read(db, team)


@router.post(
    "/tasks/{task_id}/proposals", response_model=ProposalRead, status_code=201, tags=["proposals"]
)
def create_proposal(task_id: str, data: ProposalCreate, db: Db):
    task = find(db, Task, task_id)
    find(db, Team, data.team_id)
    if not task.confirmed:
        raise HTTPException(409, "Задача ещё не опубликована")
    proposal = Proposal(**data.model_dump(), task_id=task.id)
    db.add(proposal)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Команда уже откликнулась на задачу") from None
    db.refresh(proposal)
    return proposal_read(proposal)


@router.get("/tasks/{task_id}/proposals", response_model=list[ProposalRead], tags=["proposals"])
def get_proposals(task_id: str, db: Db):
    find(db, Task, task_id)
    return [
        proposal_read(p)
        for p in db.scalars(
            select(Proposal).where(Proposal.task_id == task_id).order_by(Proposal.created_at)
        )
    ]


@router.get("/proposals", response_model=list[ProposalRead], tags=["proposals"])
def list_proposals(
    db: Db,
    team_id: str = Query("", max_length=32),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    query = select(Proposal)
    if team_id:
        find(db, Team, team_id)
        query = query.where(Proposal.team_id == team_id)
    return [
        proposal_read(p)
        for p in db.scalars(
            query.order_by(Proposal.created_at, Proposal.id).offset(offset).limit(limit)
        )
    ]


@router.patch("/proposals/{proposal_id}/decision", response_model=ProposalRead, tags=["proposals"])
def decide(proposal_id: str, data: Decision, db: Db):
    proposal = find(db, Proposal, proposal_id)
    result = db.execute(
        update(Proposal)
        .where(Proposal.id == proposal_id, Proposal.status == "pending")
        .values(status=data.decision)
    )
    if result.rowcount != 1:
        raise HTTPException(409, "Решение по отклику уже принято")
    db.commit()
    db.refresh(proposal)
    return proposal_read(proposal)


@router.post(
    "/proposals/{proposal_id}/progress",
    response_model=ProgressRead,
    status_code=201,
    tags=["proposals"],
)
def progress(proposal_id: str, data: ProgressCreate, db: Db):
    proposal = find(db, Proposal, proposal_id)
    if proposal.status != "accepted":
        raise HTTPException(409, "Этап можно подтвердить только у принятого отклика")
    db.add(Progress(proposal_id=proposal_id, stage=data.stage, points=STAGE_POINTS[data.stage]))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Этап уже подтверждён; баллы повторно не начисляются") from None
    db.refresh(proposal)
    return {
        "proposal_id": proposal.id,
        "team_id": proposal.team_id,
        "stages_done": proposal_read(proposal)["stages_done"],
        "points_total": sum(row.points for row in proposal.progress),
        "team_points_total": team_points(db, find(db, Team, proposal.team_id)),
    }
