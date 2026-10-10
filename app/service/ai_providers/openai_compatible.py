import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings
from app.core.exceptions import AIInterviewError
from app.model.ai_interview import AIInterviewMessage, AIModelConfig
from app.service.ai_providers.base import AIInterviewProvider


class OpenAICompatibleProvider(AIInterviewProvider):
    """Adapter for OpenAI-compatible streaming chat completion APIs."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    @property
    def name(self) -> str:
        return "openai_compatible"

    @staticmethod
    def _chat_url(base_url: str) -> str:
        normalized_url = base_url.rstrip("/")
        if normalized_url.endswith("/chat/completions"):
            return normalized_url
        if not normalized_url.endswith("/v1"):
            normalized_url = f"{normalized_url}/v1"
        return f"{normalized_url}/chat/completions"

    @staticmethod
    def _resolve_model_settings(
        settings: Settings,
        model_config: AIModelConfig | None,
    ) -> tuple[str, str, str]:
        """Combine request-level overrides with server-side provider settings."""
        override = model_config or AIModelConfig()
        base_url = override.base_url or settings.ai_api_base_url
        model = override.model or settings.ai_model
        api_key = (
            override.api_key.get_secret_value()
            if override.api_key
            else settings.ai_api_key
        )
        return base_url, model, api_key

    async def stream(
        self,
        messages: list[AIInterviewMessage],
        model_config: AIModelConfig | None = None,
    ) -> AsyncIterator[str]:
        base_url, model, api_key = self._resolve_model_settings(
            self.settings,
            model_config,
        )
        if not base_url:
            raise AIInterviewError("AI API URL 未配置，请检查模型配置")
        if not model:
            raise AIInterviewError("AI 模型未配置，请检查模型配置")
        if not api_key:
            raise AIInterviewError("AI API Key 未配置，请检查模型配置或 .env 配置")

        payload = {
            "model": model,
            "messages": [message.model_dump() for message in messages],
            "max_completion_tokens": self.settings.ai_max_completion_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        received = False
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.ai_timeout_seconds,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST", self._chat_url(base_url), json=payload, headers=headers
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload_text = line[5:].strip()
                        if not payload_text or payload_text == "[DONE]":
                            if payload_text == "[DONE]":
                                break
                            continue
                        try:
                            body = json.loads(payload_text)
                            choices = body.get("choices")
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                        except (AttributeError, TypeError, json.JSONDecodeError) as exc:
                            raise AIInterviewError("AI 服务返回的数据格式无效") from exc
                        if isinstance(content, str) and content:
                            received = True
                            yield content
        except httpx.HTTPStatusError as exc:
            raise AIInterviewError("AI 服务返回错误，请稍后重试") from exc
        except httpx.HTTPError as exc:
            raise AIInterviewError("无法连接 AI 服务，请检查网络和配置") from exc

        if not received:
            raise AIInterviewError("AI 服务返回了空回复")
