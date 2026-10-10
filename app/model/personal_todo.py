"""A dated task owned by one personal account."""

from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


class PersonalTodo(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    owner_id: str
    title: str = Field(min_length=1, max_length=200)
    due_date: date
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
