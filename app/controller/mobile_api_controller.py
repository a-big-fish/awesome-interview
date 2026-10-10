"""Authenticated Android snapshot and dated tasks."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response

from app.core.dependencies import (get_interview_experience_service, get_personal_schedule_service,
                                   get_personal_todo_service)
from app.service.interview_experience_service import InterviewExperienceService
from app.service.personal_schedule_service import PersonalScheduleService
from app.service.personal_todo_service import PersonalTodoService


router = APIRouter(prefix="/api/mobile/v1", tags=["mobile"])


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
