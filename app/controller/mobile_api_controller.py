"""Authenticated Android snapshot and dated tasks."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError

from app.core.dependencies import (get_interview_experience_service, get_personal_schedule_service,
                                   get_personal_todo_service)
from app.core.exceptions import PersonalEventConflictWarning
from app.core.exceptions import MeetingParseError
from app.model.personal_event import PersonalEventType
from app.service.interview_experience_service import InterviewExperienceService
from app.service.personal_schedule_service import PersonalScheduleService
from app.service.personal_todo_service import PersonalTodoService


router = APIRouter(prefix="/api/mobile/v1", tags=["mobile"])


class NativeEventInput(BaseModel):
    """Editable event fields sent by the native schedule screen."""

    title: str = Field(min_length=1, max_length=200)
    event_type: PersonalEventType
    start_at: datetime
    end_at: datetime
    timezone: str = "Asia/Shanghai"
    position: str | None = None
    location_text: str | None = None
    note: str | None = None
    reminder_offsets_minutes: list[int] = Field(default_factory=list)
    confirm_overlap: bool = False
    raw_invitation: str | None = None


class NativeInvitationInput(BaseModel):
    raw_text: str = Field(min_length=1)


class NativeCompletionInput(BaseModel):
    completed: bool = Field(strict=True)


def _event_error(error: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


@router.post("/events/parse")
def parse_event(payload: NativeInvitationInput,
                schedule: PersonalScheduleService = Depends(get_personal_schedule_service)) -> dict:
    """Parse a pasted invitation for review in the native event editor."""
    try:
        event = schedule.from_invitation(payload.raw_text)
    except (MeetingParseError, ValidationError, ValueError) as error:
        raise _event_error(error) from error
    return event.model_dump(mode="json")


@router.post("/events", status_code=201)
def create_event(payload: NativeEventInput,
                 schedule: PersonalScheduleService = Depends(get_personal_schedule_service)) -> dict:
    """Create an event with the same ownership, validation and overlap rules as Web."""
    try:
        fields = dict(title=payload.title, event_type=payload.event_type,
                      start_at=payload.start_at, end_at=payload.end_at,
                      timezone=payload.timezone, position=payload.position,
                      location_text=payload.location_text, note=payload.note,
                      reminder_offsets_minutes=payload.reminder_offsets_minutes,
                      confirm_overlap=payload.confirm_overlap)
        event = (schedule.create_from_invitation(payload.raw_invitation, **fields)
                 if payload.raw_invitation else schedule.create_manual(**fields))
    except PersonalEventConflictWarning as error:
        raise HTTPException(409, detail={"conflicts": error.event_titles}) from error
    except (ValueError, ValidationError, MeetingParseError) as error:
        raise _event_error(error) from error
    return event.model_dump(mode="json", exclude={"raw_invitation"})


@router.put("/events/{event_id}")
def update_event(event_id: str, payload: NativeEventInput,
                 schedule: PersonalScheduleService = Depends(get_personal_schedule_service)) -> dict:
    """Update one owned event and preserve its existing source metadata."""
    try:
        event = schedule.update_event(
            event_id, title=payload.title.strip(), type=payload.event_type,
            start_at=payload.start_at, end_at=payload.end_at,
            timezone=payload.timezone, position=payload.position,
            location_text=payload.location_text, note=payload.note,
            reminder_offsets_minutes=payload.reminder_offsets_minutes,
            confirm_overlap=payload.confirm_overlap,
        )
    except LookupError as error:
        raise HTTPException(404, detail=str(error)) from error
    except PersonalEventConflictWarning as error:
        raise HTTPException(409, detail={"conflicts": error.event_titles}) from error
    except (ValueError, ValidationError) as error:
        raise _event_error(error) from error
    return event.model_dump(mode="json", exclude={"raw_invitation"})


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: str,
                 schedule: PersonalScheduleService = Depends(get_personal_schedule_service)) -> None:
    """Delete one event owned by the current account."""
    if not schedule.delete_event(event_id):
        raise HTTPException(404, detail="日程不存在")


@router.post("/events/{event_id}/completion")
def complete_event(event_id: str, payload: NativeCompletionInput,
                   schedule: PersonalScheduleService = Depends(get_personal_schedule_service)) -> dict:
    """Set completion for an owned event and return its updated native detail."""
    try:
        event = schedule.set_event_completed(event_id, payload.completed)
    except LookupError as error:
        raise HTTPException(404, detail="日程不存在") from error
    return event.model_dump(mode="json", exclude={"raw_invitation"})


@router.get("/snapshot")
def snapshot(
    request: Request,
    response: Response,
    schedule: PersonalScheduleService = Depends(get_personal_schedule_service),
    experiences: InterviewExperienceService = Depends(get_interview_experience_service),
    todos: PersonalTodoService = Depends(get_personal_todo_service),
) -> dict:
    """Return one authoritative, owner-scoped snapshot for read-only offline use."""
    response.headers["Cache-Control"] = "no-store"
    notes = []
    for item in experiences.list_experiences():
        public_fields = item.model_dump(mode="json", exclude={"raw_text_draft"})
        notes.append({
            **public_fields,
            "questions": [question.model_dump(mode="json") for question in experiences.list_questions(item.id)],
        })
    return {
        "schema_version": 1,
        "user_id": request.state.user.id,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "events": [event.model_dump(mode="json", exclude={"raw_invitation"}) for event in schedule.list_events()],
        "experiences": notes,
        "todos": [todo.model_dump(mode="json") for todo in todos.list_todos()],
    }


@router.get("/session")
def session(request: Request, response: Response) -> dict:
    """Give the native client the current session's CSRF token for task writes."""
    response.headers["Cache-Control"] = "no-store"
    return {"user_id": request.state.user.id, "csrf_token": request.state.csrf_token}


@router.post("/todos", status_code=201)
def create_todo(title: str = Form(min_length=1, max_length=200), due_date: date = Form(),
                todos: PersonalTodoService = Depends(get_personal_todo_service)) -> dict:
    if not title.strip():
        raise HTTPException(422, "请输入待办内容")
    return todos.create(title, due_date).model_dump(mode="json")


@router.post("/todos/{todo_id}/toggle")
def toggle_todo(todo_id: str, todos: PersonalTodoService = Depends(get_personal_todo_service)) -> dict:
    try:
        return todos.toggle(todo_id).model_dump(mode="json")
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@router.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: str, todos: PersonalTodoService = Depends(get_personal_todo_service)) -> None:
    if not todos.delete(todo_id):
        raise HTTPException(404, "待办不存在")
