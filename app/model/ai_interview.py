"""Domain models for the AI interview assistant boundary."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr, StringConstraints


class AIInterviewMessage(BaseModel):
    """A prior dialogue turn sent to an AI provider."""

    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1)


class AIModelConfig(BaseModel):
    """Temporary, request-scoped override for a model provider."""

    base_url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2048)] | None = None
    model: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    api_key: SecretStr | None = None


class AIInterviewRequest(BaseModel):
    """Input for an AI assistant call from the interview detail page."""

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
    entry_id: str | None = None
    resume_id: str | None = None
    history: list[AIInterviewMessage] = Field(default_factory=list, max_length=40)
    system_prompt: Annotated[str, StringConstraints(strip_whitespace=True, max_length=8000)] | None = None
    ai_model_config: AIModelConfig | None = None


class AIInterviewContext(BaseModel):
    """Context status returned before the chat panel starts."""

    entry_id: str
    candidate_name: str
    position: str | None = None
    has_resume_context: bool = False
    resume_text_available: bool = False
    provider: str
    default_system_prompt: str


class AIInterviewResponse(BaseModel):
    """Output returned by the AI interview assistant service."""

    answer: str
    provider: str
    has_interview_context: bool = False
    has_resume_context: bool = False
