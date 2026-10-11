from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from app.controller.page_controller import WEEKDAY_NAMES, _assign_entry_columns, templates
from app.core.dependencies import (
    get_interview_experience_service, get_my_resume_mapper,
    get_personal_schedule_service, get_resume_parser_service,
)
from app.core.exceptions import MeetingParseError, PersonalEventConflictWarning, ResumeParseError
from app.mapper.base_my_resume_mapper import BaseMyResumeMapper
from app.model.my_resume_profile import MyResumeProfile
from app.model.personal_event import PersonalEvent
from app.service.personal_schedule_service import PersonalScheduleService
from app.service.interview_experience_service import InterviewExperienceService
from app.model.interview_experience import CATEGORY_LABELS
from app.service.resume_parser_service import ResumeParserService

router = APIRouter(prefix="/my-schedule", tags=["personal-schedule"])
DISPLAY_ZONE = ZoneInfo("Asia/Shanghai")
EVENT_LABELS = {
    "interview": "面试",
    "exam": "笔试／考试",
    "course": "课程",
    "recruiting": "招聘活动",
    "meeting": "普通会议",
    "personal": "个人事项",
}


def _event_view(event: PersonalEvent, now: datetime) -> dict[str, Any]:
    start = event.start_at.astimezone(DISPLAY_ZONE)
    end = event.end_at.astimezone(DISPLAY_ZONE)
    status = "finished" if now >= end else "ongoing" if now >= start else "upcoming"
    return {
        **event.model_dump(mode="json"),
        "start_time": start,
        "end_time": end,
        "start_minutes": start.hour * 60 + start.minute,
        "duration_minutes": int((end - start).total_seconds() // 60),
        "status": status,
        "status_label": {"finished": "已结束", "ongoing": "进行中", "upcoming": "即将开始"}[status],
        "display_name": event.title,
        "type_label": EVENT_LABELS[event.type],
    }


def _week_day_segments(events: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    """Clip events to a local calendar day for the 24-hour week timeline."""
    day_start = datetime.combine(day, datetime.min.time(), DISPLAY_ZONE)
    day_end = day_start + timedelta(days=1)
    segments = []
    for event in events:
        start = event["start_time"]
        end = event["end_time"]
        if start >= day_end or end <= day_start:
            continue
        clipped_start = max(start, day_start)
        clipped_end = min(end, day_end)
        start_minutes = int((clipped_start - day_start).total_seconds() // 60)
        end_minutes = int((clipped_end - day_start).total_seconds() // 60)
        segments.append({
            **event,
            "start_minutes": start_minutes,
            "duration_minutes": end_minutes - start_minutes,
            "continues_before": start < day_start,
            "continues_after": end > day_end,
        })
    _assign_entry_columns(segments)
    return segments


def _dashboard_context(service: PersonalScheduleService, selected_date: date,
                       selected_view: str = "day") -> dict[str, Any]:
    now = datetime.now(DISPLAY_ZONE)
    all_events = service.list_events()
    event_views = [_event_view(item, now) for item in all_events]
    views = _week_day_segments(event_views, selected_date)
    earliest = min((item["start_minutes"] // 60 for item in views), default=6)
    latest = max(((item["start_minutes"] + item["duration_minutes"] + 59) // 60
                  for item in views), default=23)
    start_hour = min(6, earliest)
    end_hour = max(23, latest)
    now_minutes = now.hour * 60 + now.minute
    upcoming = [item for item in event_views if item["end_time"] > now]
    selected_view = selected_view if selected_view in {"day", "week", "month"} else "day"
    calendar_days: list[dict[str, Any]] = []
    week_bridges: list[int] = []
    if selected_view == "week":
        period_start = selected_date - timedelta(days=selected_date.weekday())
        period_dates = [period_start + timedelta(days=offset) for offset in range(7)]
        prev_date = selected_date - timedelta(days=7)
        next_date = selected_date + timedelta(days=7)
        period_end = datetime.combine(period_dates[-1] + timedelta(days=1),
                                      datetime.min.time(), DISPLAY_ZONE)
        period_begin = datetime.combine(period_start, datetime.min.time(), DISPLAY_ZONE)
        week_count = sum(item["start_time"] < period_end and
                         item["end_time"] > period_begin for item in event_views)
        period_title = f"{period_dates[0]:%Y-%m-%d} — {period_dates[-1]:%m-%d} · {week_count} 项安排"
        week_bridges = [
            index + 1 for index, day in enumerate(period_dates[:-1])
            if any(item["start_time"] < datetime.combine(day + timedelta(days=1),
                                                          datetime.min.time(), DISPLAY_ZONE)
                   < item["end_time"] for item in event_views)
        ]
    elif selected_view == "month":
        first = selected_date.replace(day=1)
        period_start = first - timedelta(days=first.weekday())
        period_dates = [period_start + timedelta(days=offset) for offset in range(42)]
        prev_date = (first - timedelta(days=1)).replace(day=1)
        next_date = (first + timedelta(days=32)).replace(day=1)
        period_title = f"{first.year} 年 {first.month} 月 · {sum(item['start_time'].year == first.year and item['start_time'].month == first.month for item in event_views)} 项安排"
    else:
        period_dates = []
        prev_date = selected_date - timedelta(days=1)
        next_date = selected_date + timedelta(days=1)
        period_title = f"{selected_date} {WEEKDAY_NAMES[selected_date.weekday()]} · {len(views)} 项安排"
    if period_dates:
        events_by_day: dict[date, list[dict[str, Any]]] = {}
        for item in event_views:
            events_by_day.setdefault(item["start_time"].date(), []).append(item)
        calendar_days = [{
            "date": day,
            "entries": events_by_day.get(day, []),
            "week_segments": _week_day_segments(event_views, day) if selected_view == "week" else [],
            "in_month": day.month == selected_date.month,
            "is_today": day == now.date(),
            "is_selected": day == selected_date,
        } for day in period_dates]
    return {
        "selected_date": selected_date,
        "today_date": now.date(),
        "selected_view": selected_view,
        "period_title": period_title,
        "calendar_days": calendar_days,
        "week_bridges": week_bridges,
        "selected_weekday": WEEKDAY_NAMES[selected_date.weekday()],
        "prev_date": prev_date.isoformat(),
        "next_date": next_date.isoformat(),
        "entries": views,
        "upcoming": upcoming[:10],
        "time_labels": [f"{hour:02d}:00" for hour in range(start_hour, end_hour + 1)],
        "start_hour": start_hour,
        "end_hour": end_hour,
        "grid_height": (end_hour - start_hour) * 88,
        "show_now_line": selected_date == now.date() and start_hour * 60 <= now_minutes <= end_hour * 60,
        "now_minutes": now_minutes,
        "now_time": now.strftime("%H:%M"),
        "event_labels": EVENT_LABELS,
    }


def _new_page(request: Request, *, error: str | None = None, warnings: list[str] | None = None,
              values: dict[str, Any] | None = None, preview: bool = False, status_code: int = 200):
    form_values = dict(values or {})
    now = datetime.now(DISPLAY_ZONE).replace(second=0, microsecond=0)
    form_values.setdefault("start_at", now.strftime("%Y-%m-%dT%H:%M"))
    form_values.setdefault("end_at", (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"))
    return templates.TemplateResponse(request, "personal_new.html", {
        "error": error,
        "warnings": warnings or [],
        "values": form_values,
        "preview": preview,
        "event_labels": EVENT_LABELS,
    }, status_code=status_code)


@router.get("", response_class=HTMLResponse)
def personal_dashboard(
    request: Request,
    date_value: str | None = None,
    view: str = "day",
    service: PersonalScheduleService = Depends(get_personal_schedule_service),
):
    try:
        selected = date.fromisoformat(date_value) if date_value else datetime.now(DISPLAY_ZONE).date()
    except ValueError:
        selected = datetime.now(DISPLAY_ZONE).date()
    return templates.TemplateResponse(request, "personal_dashboard.html", _dashboard_context(service, selected, view))


@router.get("/new", response_class=HTMLResponse)
def new_personal_event(request: Request):
    return _new_page(request)


@router.post("/parse", response_class=HTMLResponse)
async def parse_personal_invitation(
    request: Request,
    service: PersonalScheduleService = Depends(get_personal_schedule_service),
):
    form = await request.form()
    raw_text = str(form.get("raw_text", ""))
    try:
        event = service.from_invitation(raw_text)
    except (MeetingParseError, ValidationError, ValueError) as exc:
        return _new_page(request, error=str(exc), values={"raw_text": raw_text}, status_code=422)
    return _new_page(request, preview=True, values={
        "source": "invitation",
        "raw_text": raw_text,
        "title": event.title,
        "event_type": event.type,
        "start_at": event.start_at.astimezone(DISPLAY_ZONE).strftime("%Y-%m-%dT%H:%M"),
        "end_at": event.end_at.astimezone(DISPLAY_ZONE).strftime("%Y-%m-%dT%H:%M"),
        "timezone": event.timezone,
        "platform": event.platform or "",
        "meeting_url": str(event.meeting_url) if event.meeting_url else "",
        "position": event.position or "",
    })


@router.post("/events", response_class=HTMLResponse)
async def create_personal_event(
    request: Request,
    service: PersonalScheduleService = Depends(get_personal_schedule_service),
):
    form = await request.form()
    values = {key: str(value) for key, value in form.items()}
    values["reminder_offsets_minutes"] = form.getlist("reminder_offsets_minutes")
    preview = values.get("source") == "invitation"
    try:
        start = datetime.fromisoformat(values["start_at"])
        end = datetime.fromisoformat(values["end_at"])
        common = {
            "title": values["title"],
            "event_type": values["event_type"],
            "timezone": values.get("timezone") or "Asia/Shanghai",
            "position": values.get("position") or None,
            "note": values.get("note") or None,
            "reminder_offsets_minutes": [int(value) for value in values["reminder_offsets_minutes"]],
        }
        confirmed = values.get("confirm_overlap") == "true"
        if preview:
            event = service.create_from_invitation(
                values.get("raw_text", ""),
                confirm_overlap=confirmed,
                title=common["title"], event_type=common["event_type"],
                timezone=common["timezone"], position=common["position"], note=common["note"],
                reminder_offsets_minutes=common["reminder_offsets_minutes"],
                start_at=start, end_at=end,
                platform=values.get("platform") or None,
                meeting_url=values.get("meeting_url") or None,
                location_text=values.get("location_text") or None,
            )
        else:
            event = service.create_manual(
                title=common["title"], event_type=common["event_type"],
                start_at=start, end_at=end, timezone=common["timezone"],
                location_text=values.get("location_text") or None,
                location_url=values.get("location_url") or None,
                note=common["note"], position=common["position"],
                reminder_offsets_minutes=common["reminder_offsets_minutes"],
                confirm_overlap=confirmed,
            )
    except PersonalEventConflictWarning as exc:
        return _new_page(request, warnings=exc.event_titles, values=values,
                         preview=preview, status_code=409)
    except (KeyError, ValueError, ValidationError, MeetingParseError) as exc:
        return _new_page(request, error=str(exc), values=values,
                         preview=preview, status_code=422)
    event_day = event.start_at.astimezone(DISPLAY_ZONE).date().isoformat()
    return RedirectResponse(url=f"/my-schedule?view=day&date_value={event_day}", status_code=303)


@router.get("/events/{event_id}", response_class=HTMLResponse)
def personal_event_detail(
    event_id: str, request: Request,
    service: PersonalScheduleService = Depends(get_personal_schedule_service),
):
    event = service.get_event(event_id)
    if not event:
        if request.app.state.settings.app_mode == "public_personal":
            raise HTTPException(status_code=404, detail="日程不存在")
        return RedirectResponse(url="/my-schedule", status_code=303)
    return templates.TemplateResponse(request, "personal_detail.html", {
        "event": event,
        "event_labels": EVENT_LABELS,
        "error": None,
        "warnings": [],
    })


@router.post("/events/{event_id}/edit", response_class=HTMLResponse)
async def edit_personal_event(
    event_id: str, request: Request,
    service: PersonalScheduleService = Depends(get_personal_schedule_service),
):
    form = await request.form()
    values = {key: str(value) for key, value in form.items()}
    values["reminder_offsets_minutes"] = form.getlist("reminder_offsets_minutes")
    try:
        event = service.update_event(
            event_id,
            confirm_overlap=values.get("confirm_overlap") == "true",
            title=values["title"].strip(),
            type=values["event_type"],
            start_at=datetime.fromisoformat(values["start_at"]),
            end_at=datetime.fromisoformat(values["end_at"]),
            timezone=values.get("timezone") or "Asia/Shanghai",
            location_text=values.get("location_text") or None,
            location_url=values.get("location_url") or None,
            note=values.get("note") or None,
            position=values.get("position") or None,
            reminder_offsets_minutes=[int(value) for value in values["reminder_offsets_minutes"]],
        )
    except PersonalEventConflictWarning as exc:
        current = service.get_event(event_id)
        return templates.TemplateResponse(request, "personal_detail.html", {
            "event": current, "event_labels": EVENT_LABELS,
            "error": None, "warnings": exc.event_titles, "values": values,
        }, status_code=409)
    except LookupError as exc:
        if request.app.state.settings.app_mode == "public_personal":
            raise HTTPException(status_code=404, detail="日程不存在") from exc
        return RedirectResponse(url="/my-schedule", status_code=303)
    except (KeyError, ValueError, ValidationError) as exc:
        current = service.get_event(event_id)
        return templates.TemplateResponse(request, "personal_detail.html", {
            "event": current, "event_labels": EVENT_LABELS,
            "error": str(exc), "warnings": [], "values": values,
        }, status_code=422)
    event_day = event.start_at.astimezone(DISPLAY_ZONE).date().isoformat()
    return RedirectResponse(url=f"/my-schedule?view=day&date_value={event_day}", status_code=303)


@router.post("/events/{event_id}/delete")
def delete_personal_event(
    event_id: str,
    request: Request,
    service: PersonalScheduleService = Depends(get_personal_schedule_service),
):
    deleted = service.delete_event(event_id)
    if not deleted and request.app.state.settings.app_mode == "public_personal":
        raise HTTPException(status_code=404, detail="日程不存在")
    return RedirectResponse(url="/my-schedule", status_code=303)


@router.get("/interviews", response_class=HTMLResponse)
def personal_interview_workspace(
    request: Request, date_value: str | None = None,
    service: PersonalScheduleService = Depends(get_personal_schedule_service),
    profile_mapper: BaseMyResumeMapper = Depends(get_my_resume_mapper),
    resume_service: ResumeParserService = Depends(get_resume_parser_service),
):
    try:
        selected = date.fromisoformat(date_value) if date_value else datetime.now(DISPLAY_ZONE).date()
    except ValueError:
        selected = datetime.now(DISPLAY_ZONE).date()
    context = _interview_workspace_context(service, selected, profile_mapper, resume_service)
    return templates.TemplateResponse(request, "personal_interviews.html", context)


@router.get("/interviews/{event_id}", response_class=HTMLResponse)
def personal_interview_questions(
    event_id: str, request: Request,
    category: str = "all",
    experience_id: str | None = None,
    saved: int = 0,
    service: PersonalScheduleService = Depends(get_personal_schedule_service),
    experience_service: InterviewExperienceService = Depends(get_interview_experience_service),
    profile_mapper: BaseMyResumeMapper = Depends(get_my_resume_mapper),
    resume_service: ResumeParserService = Depends(get_resume_parser_service),
):
    """Show the selected interview beside the resume with its question area."""
    event = service.get_event(event_id)
    if not event:
        if request.app.state.settings.app_mode == "public_personal":
            raise HTTPException(status_code=404, detail="日程不存在")
        return RedirectResponse(url="/my-schedule/interviews", status_code=303)
    if event.type != "interview":
        return RedirectResponse(url=f"/my-schedule/events/{event_id}", status_code=303)
    selected = event.start_at.astimezone(DISPLAY_ZONE).date()
    context = {"selected_date": selected}
    profile = profile_mapper.get(service.profile_id)
    resume = resume_service.get_resume(profile.resume_id) if profile else None
    context["my_resume"] = resume if resume and (
        service.owner_id == "local" or resume.owner_id == service.owner_id
    ) else None
    context["selected_event"] = _event_view(event, datetime.now(DISPLAY_ZONE))
    experiences = experience_service.for_event(event_id)
    experience = next((item for item in experiences if item.id == experience_id), None)
    if experience is None:
        experience = experiences[0] if experiences else None
    category = category if category in {"all", "feeling", *CATEGORY_LABELS} else "all"
    context["experience"] = experience
    context["linked_event"] = event
    context["category"] = category
    context["category_labels"] = CATEGORY_LABELS
    context["event_experiences"] = experiences
    context["question_rows"] = experience_service.numbered_questions(experience.id) if experience else []
    context["visible_rows"] = (context["question_rows"] if category == "all" else
                               experience_service.tree_rows(context["question_rows"], category) if category != "feeling" else []) if experience else []
    context["draft_seed"] = {"version": experience.updated_at.isoformat(),
                             "questions": [row["question"].model_dump(mode="json")
                                           for row in context["question_rows"]],
                             "category_minutes": experience.category_minutes,
                             "total_minutes": experience.total_minutes,
                             "feeling": experience.feeling or ""} if experience else None
    context["detail_url"] = f"/my-schedule/interviews/{event_id}?experience_id={experience.id}" if experience else f"/my-schedule/interviews/{event_id}"
    context["saved"] = saved
    return templates.TemplateResponse(request, "personal_interviews.html", context)


def _interview_workspace_context(
    service: PersonalScheduleService,
    selected: date,
    profile_mapper: BaseMyResumeMapper,
    resume_service: ResumeParserService,
) -> dict[str, Any]:
    """Adapt personal events to the original three-column interview layout."""
    context = _dashboard_context(service, selected)
    now = datetime.now(DISPLAY_ZONE)
    interview_views = [_event_view(item, now) for item in service.list_events() if item.type == "interview"]
    context["entries"] = [item for item in interview_views if item["start_time"].date() == selected]
    _assign_entry_columns(context["entries"])
    context["today_interviews"] = [item for item in interview_views if item["start_time"].date() == now.date() and item["status"] != "finished"]
    context["future_interviews"] = [item for item in interview_views if item["start_time"].date() > now.date()]
    context["finished_interviews"] = [item for item in interview_views if item["status"] == "finished"]
    start_hour = min([9, *(item["start_time"].hour for item in context["entries"])])
    end_hour = max([19, *(item["end_time"].hour + (item["end_time"].minute > 0) for item in context["entries"])])
    context["start_hour"] = start_hour
    context["end_hour"] = end_hour
    context["time_labels"] = [
        {"text": f"{minute // 60:02d}:{minute % 60:02d}", "minutes": minute}
        for minute in range(start_hour * 60, end_hour * 60 + 1, 30)
    ]
    context["show_now_line"] = selected == now.date() and start_hour * 60 <= now.hour * 60 + now.minute <= end_hour * 60
    context["now_minutes"] = now.hour * 60 + now.minute
    context["now_time"] = now.strftime("%H:%M")
    context["date_options"] = [
        {"date": day.isoformat(), "label": (
            "昨天" if day == now.date() - timedelta(days=1) else
            "今天" if day == now.date() else
            "明天" if day == now.date() + timedelta(days=1) else
            day.strftime("%m-%d")
        )}
        for day in (selected - timedelta(days=1), selected, selected + timedelta(days=1))
    ]
    profile = profile_mapper.get(service.profile_id)
    resume = resume_service.get_resume(profile.resume_id) if profile else None
    context["my_resume"] = resume if resume and (
        service.owner_id == "local" or resume.owner_id == service.owner_id
    ) else None
    return context


@router.post("/resume")
async def upload_personal_resume(
    request: Request,
    resume: UploadFile,
    service: PersonalScheduleService = Depends(get_personal_schedule_service),
    profile_mapper: BaseMyResumeMapper = Depends(get_my_resume_mapper),
    resume_service: ResumeParserService = Depends(get_resume_parser_service),
):
    try:
        parsed = await resume_service.parse_upload(resume, owner_id=service.owner_id)
    except ResumeParseError as exc:
        context = _interview_workspace_context(service, datetime.now(DISPLAY_ZONE).date(), profile_mapper, resume_service)
        context["resume_error"] = str(exc)
        return templates.TemplateResponse(request, "personal_interviews.html", context, status_code=422)
    profile_mapper.save(MyResumeProfile(id=service.profile_id, resume_id=parsed.id))
    return RedirectResponse(url="/my-schedule/interviews", status_code=303)
