from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    field_validator,
    model_validator,
)

Level = Literal["draft", "working", "ready", "priority"]
Stage = Literal["prototype", "testing", "final"]
Text = Annotated[str, Field(max_length=5000)]
Tag = Annotated[str, Field(min_length=1, max_length=100)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Card(Input):
    title: str = Field(default="", max_length=200)
    topic: str = Field(default="", max_length=100)
    context: Text = ""
    need: Text = ""
    users: Text = ""
    data: Text = ""
    constraints: Text = ""
    expected_result: Text = ""
    success_criteria: Text = ""
    contact: str = Field(default="", max_length=500)
    interaction_format: Text = ""


CardField = Literal[
    "title",
    "topic",
    "context",
    "need",
    "users",
    "data",
    "constraints",
    "expected_result",
    "success_criteria",
    "contact",
    "interaction_format",
]


class CardRequest(Input):
    card: Card


class TaskCreate(CardRequest):
    confirmed: bool = False
    owner_id: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def check_publication(self):
        if self.confirmed and (not self.card.title or not self.card.topic):
            raise ValueError("Для публикации заполните название и тему")
        return self


class TaskUpdate(Input):
    card: Card | None = None
    confirmed: bool | None = None

    @model_validator(mode="after")
    def reject_empty(self):
        if self.card is None and self.confirmed is None:
            raise ValueError("Передайте card или confirmed")
        return self


class Breakdown(BaseModel):
    field: str
    label: str
    max: int
    earned: int
    reason: str


class Missing(BaseModel):
    field: str
    hint: str
    potential_points: int


class Score(BaseModel):
    score: int
    level: Level
    breakdown: list[Breakdown]
    missing: list[Missing]


class ParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    role: Literal["business", "student"]
    organization: str
    bio: str
    interests: list[str]
    skills: list[str]
    is_demo: bool
    team_id: str | None


class TopicRead(BaseModel):
    topic: str
    tasks_count: int


class TaskSummary(BaseModel):
    id: str
    title: str
    topic: str
    need: str
    score: int
    level: Level
    confirmed: bool
    proposals_count: int
    created_at: datetime
    owner: ParticipantRead | None = None
    is_demo: bool = False
    work_tags: list[str] = Field(default_factory=list)


class TeamCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    contact: str = Field(default="", max_length=500)
    interests: list[Tag] = Field(default_factory=list, max_length=30)
    skills: list[Tag] = Field(default_factory=list, max_length=30)
    tech: list[Tag] = Field(default_factory=list, max_length=30)


class TeamRead(TeamCreate):
    id: str
    points: int
    is_demo: bool = False
    members: list[ParticipantRead] = Field(default_factory=list)


class ProposalCreate(Input):
    team_id: str = Field(min_length=1, max_length=32)
    idea: str = Field(min_length=1, max_length=5000)
    plan: str = Field(min_length=1, max_length=5000)
    deadline: date
    prototype_url: str = Field(default="", max_length=2048)

    @field_validator("prototype_url")
    @classmethod
    def validate_url(cls, value):
        if value:
            TypeAdapter(HttpUrl).validate_python(value)
        return value


class ProposalRead(ProposalCreate):
    id: str
    task_id: str
    status: Literal["pending", "accepted", "rejected"]
    stages_done: list[Stage]
    created_at: datetime


class TaskRead(Score):
    id: str
    card: Card
    confirmed: bool
    created_at: datetime
    updated_at: datetime
    proposals: list[ProposalRead]
    owner: ParticipantRead | None = None
    is_demo: bool = False
    work_tags: list[str] = Field(default_factory=list)


class Decision(Input):
    decision: Literal["accepted", "rejected"]


class ProgressCreate(Input):
    stage: Stage


class ProgressRead(BaseModel):
    proposal_id: str
    team_id: str
    stages_done: list[Stage]
    points_total: int
    team_points_total: int


class AnalyzeRequest(Input):
    draft_text: str = Field(max_length=20000)
    topic: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def require_input(self):
        if not self.draft_text and not self.topic:
            raise ValueError("Опишите задачу или укажите тему")
        return self


class Question(Input):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    field: CardField
    question: str = Field(min_length=1, max_length=1000)


class AnalysisResult(Input):
    questions: list[Question] = Field(min_length=3, max_length=5)
    filled_fields: list[CardField] = Field(max_length=11)
    missing_fields: list[CardField] = Field(max_length=11)

    @model_validator(mode="after")
    def unique_questions_and_fields(self):
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Идентификаторы вопросов должны быть уникальными")
        if len({q.field for q in self.questions}) != len(self.questions):
            raise ValueError("Один вопрос на каждое поле")
        for fields in (self.filled_fields, self.missing_fields):
            if len(set(fields)) != len(fields):
                raise ValueError("Список полей содержит повторения")
        if set(self.filled_fields) & set(self.missing_fields):
            raise ValueError("Поле не может быть одновременно заполненным и отсутствующим")
        return self


class AnalyzeRead(AnalysisResult):
    mode: Literal["demo", "openai"] = "demo"


class Answer(Input):
    question_id: str = Field(min_length=1, max_length=100)
    field: CardField
    answer: Text


class BuildRequest(AnalyzeRequest):
    answers: list[Answer] = Field(default_factory=list, max_length=11)

    @model_validator(mode="after")
    def unique_fields(self):
        if len({answer.field for answer in self.answers}) != len(self.answers):
            raise ValueError("Один ответ на каждое поле")
        return self


class BuildResult(Input):
    card: Card
    warnings: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(max_length=20)


class BuildRead(BuildResult):
    mode: Literal["demo", "openai"] = "demo"


class BusinessRank(BaseModel):
    rank: int
    profile: ParticipantRead
    points: int
    published_tasks: int
    average_readiness: float
    completed_tasks: int
    open_tasks: int


class TeamRank(BaseModel):
    rank: int
    team: TeamRead
    points: int
    completed_tasks: int
    confirmed_stages: int


class LeaderboardRead(BaseModel):
    period: Literal["month", "all"]
    starts_at: datetime | None
    as_of: datetime
    businesses: list[BusinessRank]
    teams: list[TeamRank]


class PublicTaskSummary(TaskSummary):
    open_for_proposals: bool


class BusinessProfileRead(BaseModel):
    profile: ParticipantRead
    contacts: list[str]
    tasks: list[PublicTaskSummary]
    total_tasks: int
    open_tasks: int


class TeamProjectRead(BaseModel):
    task: PublicTaskSummary
    stages_done: list[Stage]
    prototype_url: str


class TeamProfileRead(BaseModel):
    team: TeamRead
    projects: list[TeamProjectRead]
    total_projects: int
