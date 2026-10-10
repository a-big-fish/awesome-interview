from pydantic import BaseModel

from app.controller.schema.common import ApiResponseVO
from app.model.ai_interview import AIInterviewContext


class AIInterviewContextVO(BaseModel):
    entry_id: str
    candidate_name: str
    position: str | None = None
    has_resume_context: bool = False
    resume_text_available: bool = False
    provider: str
    default_system_prompt: str

    @classmethod
    def from_domain(cls, context: AIInterviewContext) -> "AIInterviewContextVO":
        return cls(**context.model_dump())
