from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.model.meeting_entry import MeetingEntry


class MeetingEntryVO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_name: str
    position: str | None = None
    subject: str
    kind: Literal["interview", "meeting"] = "interview"
    start_time: datetime
    end_time: datetime
    platform: str
    room_number: str | None = None
    meeting_url: str | None = None
    interviewer_names: list[str] = []
    status: Literal["upcoming", "ongoing", "finished"]
    resume_id: str | None = None
    note: str | None = None

    @classmethod
    def from_domain(cls, entry: MeetingEntry, current_time: datetime) -> "MeetingEntryVO":
        data = entry.model_dump(mode="json")
        data["status"] = entry.status_at(current_time).value
        return cls.model_validate(data)
