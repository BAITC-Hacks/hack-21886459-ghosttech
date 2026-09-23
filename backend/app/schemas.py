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


class TeamCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    interests: list[Tag] = Field(default_factory=list, max_length=30)
    skills: list[Tag] = Field(default_factory=list, max_length=30)
    tech: list[Tag] = Field(default_factory=list, max_length=30)


class TeamRead(TeamCreate):
    id: str
    points: int


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


class Question(BaseModel):
    id: str
    field: CardField
    question: str


class AnalyzeRead(BaseModel):
    questions: list[Question]
    filled_fields: list[CardField]
    missing_fields: list[CardField]
    mode: Literal["demo"] = "demo"


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


class BuildRead(BaseModel):
    card: Card
    warnings: list[str]
