from collections.abc import AsyncIterator

from app.model.ai_interview import AIInterviewMessage, AIModelConfig
from app.service.ai_providers.base import AIInterviewProvider


class StaticAIInterviewProvider(AIInterviewProvider):
    """Deterministic provider used for local development and tests."""

    @property
    def name(self) -> str:
        return "static"

    async def stream(
        self,
        messages: list[AIInterviewMessage],
        model_config: AIModelConfig | None = None,
    ) -> AsyncIterator[str]:
        question = messages[-1].content if messages else ""
        text = (
            "AI 面试辅助入口已就绪。当前使用本地静态 Provider，"
            f'收到的问题："{question}"。配置远程模型后即可返回真实回复。'
        )
        for index in range(0, len(text), 8):
            yield text[index:index + 8]
