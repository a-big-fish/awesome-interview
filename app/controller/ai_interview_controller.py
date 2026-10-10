import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.controller.schema.ai_interview_dto import AIInterviewChatDTO
from app.controller.schema.ai_interview_vo import AIInterviewContextVO
from app.controller.schema.common import ApiResponseVO
from app.core.dependencies import get_ai_interview_service
from app.core.exceptions import AIInterviewError
from app.model.ai_interview import AIInterviewMessage, AIInterviewResponse
from app.service.ai_interview_service import AIInterviewService

router = APIRouter(prefix="/api/v1/interviews", tags=["ai-interview"])


@router.get("/{entry_id}/ai/context", response_model=ApiResponseVO[AIInterviewContextVO])
def get_ai_context(
    entry_id: str,
    service: AIInterviewService = Depends(get_ai_interview_service),
) -> ApiResponseVO[AIInterviewContextVO]:
    """Load interview and resume context status when the AI panel is opened."""
    try:
        context = service.get_context(entry_id)
    except AIInterviewError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponseVO[AIInterviewContextVO](data=AIInterviewContextVO.from_domain(context))


@router.post("/{entry_id}/ai/chat", response_model=ApiResponseVO[AIInterviewResponse])
async def chat_with_ai(
    entry_id: str,
    dto: AIInterviewChatDTO,
    service: AIInterviewService = Depends(get_ai_interview_service),
) -> ApiResponseVO[AIInterviewResponse]:
    """Send one interview question and return the complete answer."""
    try:
        response = await service.ask(dto.model_copy(update={"entry_id": entry_id}))
    except AIInterviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponseVO[AIInterviewResponse](data=response)


def _sse_event(payload: dict[str, str]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/{entry_id}/ai/chat/stream")
async def stream_chat_with_ai(
    entry_id: str,
    dto: AIInterviewChatDTO,
    service: AIInterviewService = Depends(get_ai_interview_service),
) -> StreamingResponse:
    """Stream an AI answer as Server-Sent Events."""
    request = dto.model_copy(update={"entry_id": entry_id})
    try:
        messages = service.prepare_messages(request)
    except AIInterviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for chunk in service.stream_messages(messages, request.ai_model_config):
                yield _sse_event({"type": "delta", "content": chunk})
            yield _sse_event({"type": "done", "provider": service.provider.name})
        except AIInterviewError as exc:
            yield _sse_event({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )
