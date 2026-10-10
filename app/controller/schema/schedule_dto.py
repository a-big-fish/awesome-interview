from pydantic import BaseModel, Field, field_validator
from app.model.meeting_entry import MeetingEntry


class MeetingEntryCreateDTO(BaseModel):
    raw_text: str
    candidate_name: str | None = None
    position: str | None = None
    interviewer_names: list[str] = Field(default_factory=list)
    note: str | None = None
    source: str = "manual"
    source_id: str | None = None
    candidate_external_id: str | None = None
    resume_id: str | None = None

    @field_validator("interviewer_names", mode="before")
    @classmethod
    def split_names(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []
