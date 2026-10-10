from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from interviewschedule.utils.time_utils import ensure_timezone


class MyResumeProfile(BaseModel):
    """The user's own resume profile for the my-interview workspace."""

    id: str = "default"
    resume_id: str
    updated_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="after")
    def validate_timezone(self) -> "MyResumeProfile":
        self.updated_at = ensure_timezone(self.updated_at)
        return self
