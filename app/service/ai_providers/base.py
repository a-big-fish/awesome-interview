from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.model.ai_interview import AIInterviewMessage, AIModelConfig


class AIInterviewProvider(ABC):
    """Pluggable boundary for remote model providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name returned to clients for diagnostics."""
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        messages: list[AIInterviewMessage],
        model_config: AIModelConfig | None = None,
    ) -> AsyncIterator[str]:
        """Yield assistant reply chunks from a complete message list."""
        raise NotImplementedError
        yield
