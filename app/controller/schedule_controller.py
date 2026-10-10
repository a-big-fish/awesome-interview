from datetime import date as date_type
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.controller.schema.common import ApiResponseVO
from app.controller.schema.schedule_dto import MeetingEntryCreateDTO
from app.controller.schema.schedule_vo import MeetingEntryVO
from app.core.dependencies import get_schedule_service
from app.core.exceptions import EntryNotFoundError, MeetingParseError, ScheduleConflictWarning
from app.service.schedule_service import ScheduleService

router = APIRouter(prefix="/api/v1/interviews", tags=["interviews"])


@router.post("", response_model=ApiResponseVO[MeetingEntryVO])
def create_interview(
    dto: MeetingEntryCreateDTO,
    confirm_non_working: bool = False,
    service: ScheduleService = Depends(get_schedule_service),
) -> JSONResponse:
    try:
        entry = service.create_from_invitation(dto, confirm_non_working=confirm_non_working)
    except MeetingParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ScheduleConflictWarning as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "warnings": exc.warnings, "confirm_non_working": True},
        ) from exc
    body = ApiResponseVO[MeetingEntryVO](
        data=MeetingEntryVO.from_domain(entry, datetime.now(entry.start_time.tzinfo))
    )
    return JSONResponse(status_code=201, content=body.model_dump(mode="json"))


@router.get("", response_model=ApiResponseVO[list[MeetingEntryVO]])
def list_interviews(
    date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    service: ScheduleService = Depends(get_schedule_service),
) -> ApiResponseVO[list[MeetingEntryVO]]:
    current = datetime.now()
    if date:
        date_type.fromisoformat(date)
        entries = service.get_daily_schedule(date)
    else:
        entries = service.list_non_personal()
    return ApiResponseVO[list[MeetingEntryVO]](
        data=[MeetingEntryVO.from_domain(entry, current) for entry in entries]
    )


@router.get("/{entry_id}", response_model=ApiResponseVO[MeetingEntryVO])
def get_interview(
    entry_id: str,
    service: ScheduleService = Depends(get_schedule_service),
) -> ApiResponseVO[MeetingEntryVO]:
    try:
        entry = service.get_entry(entry_id)
    except EntryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponseVO[MeetingEntryVO](
        data=MeetingEntryVO.from_domain(entry, datetime.now(entry.start_time.tzinfo))
    )


@router.delete("/{entry_id}", response_model=ApiResponseVO[None])
def delete_interview(
    entry_id: str,
    service: ScheduleService = Depends(get_schedule_service),
) -> ApiResponseVO[None]:
    try:
        service.delete_entry(entry_id)
    except EntryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponseVO[None](message="面试记录已删除")
