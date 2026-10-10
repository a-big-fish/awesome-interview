from datetime import datetime
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, HttpUrl, model_validator

from interviewschedule.utils.time_utils import ensure_timezone

PersonalEventType = Literal[
    "interview", "exam", "course", "recruiting", "meeting", "personal"
]


class PersonalEvent(BaseModel):
    """An event owned by the job seeker's independent schedule."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    owner_id: str = "local"
    type: PersonalEventType
    title: str = Field(min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime
    timezone: str = "Asia/Shanghai"
    location_text: str | None = None
    location_url: HttpUrl | None = None
    note: str | None = None
    source: Literal["manual", "invitation", "migrated"] = "manual"
    raw_invitation: str | None = None
    position: str | None = None
    platform: str | None = None
    room_number: str | None = None
    meeting_url: HttpUrl | None = None
    resume_id: str | None = None
    legacy_entry_id: str | None = None
    attachment_refs: list[str] = Field(default_factory=list)
    reminder_offsets_minutes: list[int] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="after")
    def validate_event(self) -> "PersonalEvent":
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("时区无效") from exc
        self.start_at = ensure_timezone(self.start_at)
        self.end_at = ensure_timezone(self.end_at)
        self.created_at = ensure_timezone(self.created_at)
        self.updated_at = ensure_timezone(self.updated_at)
        if self.end_at <= self.start_at:
            raise ValueError("结束时间必须晚于开始时间")
        if self.type != "interview" and self.resume_id:
            raise ValueError("只有面试事件可以关联简历")
        allowed_reminders = {10, 60, 1440}
        if len(self.reminder_offsets_minutes) != len(set(self.reminder_offsets_minutes)) or not set(self.reminder_offsets_minutes) <= allowed_reminders:
            raise ValueError("提醒时间无效")
        self.reminder_offsets_minutes.sort()
        return self
