from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCORED_FIELDS = (
    "context",
    "need",
    "data",
    "expected_result",
    "success_criteria",
    "constraints",
    "users",
    "contact",
    "interaction_format",
)
CARD_FIELDS = ("title", "topic", *SCORED_FIELDS)
FieldName = Literal[
    "context",
    "need",
    "data",
    "expected_result",
    "success_criteria",
    "constraints",
    "users",
    "contact",
    "interaction_format",
]


class AIInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AnalyzeInput(AIInput):
    draft_text: str = Field(min_length=10, max_length=3000)
    topic: str = Field(min_length=1, max_length=60)


class AnswerInput(AIInput):
    question_id: str = Field(min_length=1, max_length=100)
    field: FieldName
    answer: str = Field(max_length=1000)


class BuildCardInput(AnalyzeInput):
    answers: list[AnswerInput] = Field(default_factory=list, max_length=10)


class Question(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    field: FieldName
    question: str = Field(min_length=1, max_length=300)


class AnalyzeModel(BaseModel):
    questions: list[Question] = Field(min_length=1, max_length=5)
    filled_fields: list[FieldName] = Field(default_factory=list)
    missing_fields: list[FieldName] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fields(self):
        if len(set(self.filled_fields)) != len(self.filled_fields):
            raise ValueError("filled_fields содержит повторы")
        if len(set(self.missing_fields)) != len(self.missing_fields):
            raise ValueError("missing_fields содержит повторы")
        if set(self.filled_fields) & set(self.missing_fields):
            raise ValueError("Поле не может быть заполнено и пропущено одновременно")
        return self


class AnalyzeOutput(AnalyzeModel):
    mode: Literal["ai", "demo"]


class BuildModel(BaseModel):
    card: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class BuildOutput(BuildModel):
    mode: Literal["ai", "demo"]
