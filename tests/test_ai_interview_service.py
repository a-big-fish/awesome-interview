import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.controller.schema.common import ApiResponseVO
from app.core.config import Settings
from app.core.dependencies import get_ai_interview_service, get_schedule_service
from app.core.exceptions import AIInterviewError
from app.mapper.base_resume_file_storage import ResumeFileStorage
from app.mapper.memory_resume_mapper import MemoryResumeMapper
from app.mapper.memory_schedule_mapper import MemoryScheduleMapper
from app.model.ai_interview import AIInterviewMessage, AIModelConfig, AIInterviewRequest
from app.model.meeting_entry import MeetingEntry
from app.model.resume import Resume
from app.service.ai_interview_service import AIInterviewService
from app.service.ai_providers.base import AIInterviewProvider
from app.service.ai_providers.openai_compatible import OpenAICompatibleProvider
from app.service.ai_providers.static import StaticAIInterviewProvider


def build_service(
    provider: AIInterviewProvider | None = None,
    resume: Resume | None = None,
    entry_resume_id: str | None = None,
) -> tuple[AIInterviewService, MeetingEntry]:
    entry = MeetingEntry(
        candidate_name="张三",
        position="后端工程师",
        subject="后端面试",
        start_time="2026-09-10T10:00:00+08:00",
        end_time="2026-09-10T10:30:00+08:00",
        resume_id=entry_resume_id,
    )
    schedule_mapper = MemoryScheduleMapper()
    resume_mapper = MemoryResumeMapper()
    schedule_mapper.save(entry)
    if resume:
        resume_mapper.save(resume)
    service = AIInterviewService(
        schedule_mapper=schedule_mapper,
        resume_mapper=resume_mapper,
        file_storage=MemoryResumeTextStorage() if resume else None,
        provider=provider or StaticAIInterviewProvider(),
        settings=Settings(_env_file=None),
    )
    return service, entry


class MemoryResumeTextStorage(ResumeFileStorage):
    def __init__(self, text: str = "候选人简历文本") -> None:
        self.text = text

    def save_pdf(self, content: bytes, file_name: str, resume_id: str) -> str:
        return "resumes/test.pdf"

    def read_pdf(self, storage_key: str) -> bytes:
        return b""

    def save_image(self, content: bytes, resume_id: str, image_id: str) -> str:
        return "resume_images/test.png"

    def read_image(self, storage_key: str) -> bytes:
        return b""

    def save_text(self, content: str, resume_id: str) -> str:
        self.text = content
        return f"resume_info/{resume_id}.txt"

    def read_text(self, storage_key: str) -> str:
        return self.text


def test_ask_returns_static_answer_with_context_flags():
    resume = Resume(
        file_name="resume.pdf",
        pdf_path="resumes/resume.pdf",
        text_path="resume_info/resume.txt",
    )
    service, entry = build_service(resume=resume, entry_resume_id=resume.id)
    response = asyncio.run(
        service.ask(
            AIInterviewRequest(
                question="总结候选人经历",
                entry_id=entry.id,
                resume_id=resume.id,
            )
        )
    )

    assert response.provider == "static"
    assert response.has_interview_context is True
    assert response.has_resume_context is True
    assert "收到的问题" in response.answer


def test_ask_builds_fixed_context_custom_prompt_and_history():
    class CaptureProvider(AIInterviewProvider):
        name = "capture"

        def __init__(self) -> None:
            self.messages = []

        async def stream(
            self,
            messages: list[AIInterviewMessage],
            model_config: AIModelConfig | None = None,
        ):
            self.messages = messages
            self.model_config = model_config
            yield "回复"

    resume = Resume(
        file_name="resume.pdf",
        pdf_path="resumes/resume.pdf",
        text_path="resume_info/resume.txt",
    )
    provider = CaptureProvider()
    service, entry = build_service(provider, resume, resume.id)
    response = asyncio.run(
        service.ask(
            AIInterviewRequest(
                question="新问题",
                entry_id=entry.id,
                resume_id=resume.id,
                system_prompt="自定义提示词",
                history=[AIInterviewMessage(role="user", content="旧问题")],
            )
        )
    )

    assert response.answer == "回复"
    assert [message.role for message in provider.messages] == [
        "system",
        "user",
        "user",
        "user",
    ]
    assert provider.messages[0].content == "自定义提示词"
    assert "面试岗位：后端工程师" in provider.messages[1].content
    assert "候选人姓名：张三" in provider.messages[1].content
    assert "候选人简历文本" in provider.messages[1].content
    assert provider.messages[2].content == "旧问题"
    assert provider.messages[-1].content == "新问题"


def test_ask_requires_resume_when_entry_has_resume_id():
    resume = Resume(
        file_name="resume.pdf",
        pdf_path="resumes/resume.pdf",
        text_path="resume_info/resume.txt",
    )
    service, entry = build_service(entry_resume_id=resume.id)

    with pytest.raises(AIInterviewError, match="简历不存在"):
        asyncio.run(
            service.ask(AIInterviewRequest(question="问题", entry_id=entry.id))
        )


def test_openai_compatible_provider_streams_remote_sse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = request.read().decode()
        assert body.find('"stream":true') >= 0
        assert body.find("custom prompt") >= 0
        content = (
            b'data: {"choices":[{"delta":{"content":"remote "}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"reply"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(200, content=content)

    settings = Settings(
        _env_file=None,
        ai_provider="openai_compatible",
        ai_api_key="test-key",
        ai_model="test-model",
    )
    provider = OpenAICompatibleProvider(settings, transport=httpx.MockTransport(handler))

    async def collect() -> str:
        return "".join(
            [
                chunk
                async for chunk in provider.stream(
                    [
                        AIInterviewMessage(role="system", content="custom prompt"),
                        AIInterviewMessage(role="user", content="question"),
                    ]
                )
            ]
        )

    assert asyncio.run(collect()) == "remote reply"


def test_openai_compatible_provider_uses_request_model_config():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "custom.example"
        assert request.url.path == "/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer request-key"
        body = request.read().decode()
        assert body.find('"model":"request-model"') >= 0
        return httpx.Response(
            200,
            content=(
                b'data: {"choices":[{"delta":{"content":"reply"}}]}\n\n'
                b"data: [DONE]\n\n"
            ),
        )

    settings = Settings(
        _env_file=None,
        ai_provider="openai_compatible",
        ai_api_base_url="https://api.openai.com/v1",
        ai_api_key="server-key",
        ai_model="server-model",
    )
    provider = OpenAICompatibleProvider(settings, transport=httpx.MockTransport(handler))
    model_config = AIModelConfig(
        base_url="https://custom.example/api",
        model="request-model",
        api_key=SecretStr("request-key"),
    )

    async def collect() -> str:
        return "".join(
            [
                chunk
                async for chunk in provider.stream(
                    [AIInterviewMessage(role="user", content="question")],
                    model_config,
                )
            ]
        )

    assert asyncio.run(collect()) == "reply"


def test_openai_compatible_provider_requires_api_key_for_custom_url():
    settings = Settings(_env_file=None, ai_provider="openai_compatible")
    provider = OpenAICompatibleProvider(settings)

    async def collect() -> str:
        return "".join(
            [
                chunk
                async for chunk in provider.stream(
                    [AIInterviewMessage(role="user", content="question")],
                    AIModelConfig(base_url="https://custom.example/api"),
                )
            ]
        )

    with pytest.raises(AIInterviewError, match="API Key"):
        asyncio.run(collect())


def test_static_provider_ignores_request_model_config():
    provider = StaticAIInterviewProvider()
    model_config = AIModelConfig(
        base_url="https://custom.example/api",
        model="ignored",
        api_key=SecretStr("ignored"),
    )

    async def collect() -> str:
        return "".join(
            [
                chunk
                async for chunk in provider.stream(
                    [AIInterviewMessage(role="user", content="question")],
                    model_config,
                )
            ]
        )

    assert asyncio.run(collect()).startswith("AI 面试辅助")


def test_ai_api_loads_context_and_chat():
    resume = Resume(
        file_name="resume.pdf",
        pdf_path="resumes/resume.pdf",
        text_path="resume_info/resume.txt",
    )
    service, entry = build_service(resume=resume, entry_resume_id=resume.id)

    class TestClientApplication:
        pass

    from app.main import app

    app.dependency_overrides[get_ai_interview_service] = lambda: service
    client = TestClient(app)
    try:
        context_response = client.get(f"/api/v1/interviews/{entry.id}/ai/context")
        assert context_response.status_code == 200
        assert context_response.json()["data"]["resume_text_available"] is True

        chat_response = client.post(
            f"/api/v1/interviews/{entry.id}/ai/chat",
            json={"question": "生成面试问题"},
        )
        assert chat_response.status_code == 200
        assert chat_response.json()["data"]["answer"].startswith("AI 面试辅助")
    finally:
        app.dependency_overrides.pop(get_ai_interview_service, None)


def test_ai_api_streams_chat_events():
    resume = Resume(
        file_name="resume.pdf",
        pdf_path="resumes/resume.pdf",
        text_path="resume_info/resume.txt",
    )
    service, entry = build_service(resume=resume, entry_resume_id=resume.id)

    from app.main import app

    app.dependency_overrides[get_ai_interview_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.post(
            f"/api/v1/interviews/{entry.id}/ai/chat/stream",
            json={"question": "question"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert '"type": "delta"' in response.text
        assert '"provider": "static"' in response.text
    finally:
        app.dependency_overrides.pop(get_ai_interview_service, None)


def test_ask_rejects_blank_question():
    service = AIInterviewService()

    with pytest.raises(ValidationError):
        asyncio.run(service.ask(AIInterviewRequest(question="   ")))
