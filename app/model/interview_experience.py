"""Personal interview notes, independent of schedule events."""

from datetime import datetime
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field


QuestionCategory = Literal["project", "fundamentals", "algorithm", "other", "reverse"]
CATEGORY_LABELS: dict[str, str] = {
    "project": "项目问题",
    "fundamentals": "八股问题",
    "algorithm": "算法题",
    "other": "其他",
    "reverse": "反问",
}


def _now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


class InterviewExperience(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    owner_id: str
    title: str = Field(min_length=1, max_length=200)
    linked_event_id: str | None = None
    company: str | None = Field(default=None, max_length=200)
    position: str | None = Field(default=None, max_length=200)
    interviewed_at: datetime | None = None
    feeling: str | None = Field(default=None, max_length=20000)
    is_public: bool = True
    interview_round: str | None = Field(default=None, max_length=50)
    review_status: str = "not_required"
    raw_text_draft: str = Field(default="", max_length=100000)
    category_minutes: dict[str, int] = Field(default_factory=dict)
    total_minutes: int | None = Field(default=None, ge=0, le=1440)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class InterviewQuestion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    experience_id: str
    parent_question_id: str | None = None
    category: QuestionCategory
    asked_order: int = Field(ge=1)
    sibling_order: int | None = Field(default=None, ge=1)
    question_text: str = Field(min_length=1, max_length=2000)
    on_site_answer: str | None = Field(default=None, max_length=20000)
    review_answer: str | None = Field(default=None, max_length=20000)
    interviewer_answer: str | None = Field(default=None, max_length=20000)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
