from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, model_validator

from interviewschedule.utils.time_utils import ensure_timezone
from app.model.enums import EntryStatus, MeetingSource


class MeetingEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    candidate_name: str
    position: str | None = None
    subject: str
    kind: Literal["interview", "meeting"] = "interview"
    start_time: datetime
    end_time: datetime
    platform: str = "未识别会议平台"
    room_number: str | None = None
    meeting_url: HttpUrl | None = None
    interviewer_names: list[str] = Field(default_factory=list)
    source: Literal["manual", "upstream", "personal"] = MeetingSource.MANUAL.value
    source_id: str | None = None
    candidate_external_id: str | None = None
    note: str | None = None
    raw_text: str | None = None
    resume_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="after")
    def validate_and_normalize(self) -> "MeetingEntry":
        self.start_time = ensure_timezone(self.start_time)
        self.end_time = ensure_timezone(self.end_time)
        if self.end_time <= self.start_time:
            raise ValueError("会议结束时间必须晚于开始时间")
        return self

    @property
    def date(self) -> str:
        return self.start_time.date().isoformat()

    def status_at(self, current_time: datetime) -> EntryStatus:
        current_time = ensure_timezone(current_time)
        if current_time >= self.end_time:
            return EntryStatus.FINISHED
        if current_time >= self.start_time:
            return EntryStatus.ONGOING
        return EntryStatus.UPCOMING
