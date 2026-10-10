from datetime import date as date_type, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from pydantic import ValidationError

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.controller.schema.schedule_dto import MeetingEntryCreateDTO
from app.core.dependencies import get_enterprise_calendar_service, get_my_interview_service, get_resume_parser_service, get_schedule_service
from app.core.exceptions import EntryNotFoundError, MeetingParseError, MyResumeNotFoundError, ResumeParseError, ScheduleConflictWarning
from app.service.meeting_parser_service import MeetingParserService
from app.service.my_interview_service import MyInterviewService
from app.service.resume_parser_service import ResumeParserService
from app.service.schedule_service import ScheduleService
from app.service.enterprise_calendar_service import EnterpriseCalendarService
from app.model.enterprise_calendar import EnterpriseCalendarSettings

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")

_STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"


def _asset_url(path: str) -> str:
    """Return a static asset URL with a cache-busting mtime version."""
    file_path = _STATIC_ROOT / path
    version = int(file_path.stat().st_mtime) if file_path.exists() else 0
    return f"/static/{path}?v={version}"


templates.env.globals["asset_url"] = _asset_url
WEEKDAY_NAMES = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
STATUS_LABELS = {
    "upcoming": "即将开始",
    "ongoing": "进行中",
    "finished": "已结束",
}


def _time_options() -> list[str]:
    return [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)] + ["24:00"]


def _build_entry_view(entry: Any, now: datetime, display_zone: ZoneInfo | None = None) -> dict[str, Any]:
    view = entry.model_dump(mode="json")
    view["platform"] = MeetingParserService.display_platform(entry)
    status = entry.status_at(now).value
    candidate_name = entry.candidate_name.strip()
    display_start = entry.start_time.astimezone(display_zone) if display_zone else entry.start_time
    display_end = entry.end_time.astimezone(display_zone) if display_zone else entry.end_time
    view.update(
        {
            "display_name": entry.subject if entry.kind == "meeting" else (candidate_name if candidate_name and candidate_name != "\u672a\u586b\u5199\u5019\u9009\u4eba" else entry.subject),
            "status": status,
            "status_label": STATUS_LABELS[status],
            "start_time": display_start,
            "end_time": display_end,
            "start_minutes": display_start.hour * 60 + display_start.minute,
            "duration_minutes": int((entry.end_time - entry.start_time).total_seconds() // 60),
        }
    )
    return view

def _assign_entry_columns(entry_views: list[dict[str, Any]]) -> None:
    """Assign CSS grid columns for overlapping entries."""
    if not entry_views:
        return

    ordered = sorted(entry_views, key=lambda e: (e["start_minutes"], -(e["duration_minutes"])))
    clusters: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_end: int | None = None
    for entry in ordered:
        start = entry["start_minutes"]
        end = start + entry["duration_minutes"]
        if current and start >= current_end:
            clusters.append(current)
            current = []
            current_end = None
        current.append(entry)
        current_end = end if current_end is None else max(current_end, end)
    if current:
        clusters.append(current)

    for cluster in clusters:
        column_ends: list[int] = []
        for entry in cluster:
            start = entry["start_minutes"]
            end = start + entry["duration_minutes"]
            for index, last_end in enumerate(column_ends):
                if last_end <= start:
                    column_ends[index] = end
                    entry["column"] = index + 1
                    break
            else:
                column_ends.append(end)
                entry["column"] = len(column_ends)
        width = len(column_ends)
        for entry in cluster:
            entry["columns"] = width


def _select_candidate_photo(resume: Any) -> Any | None:
    """优先取简历解析时标记的证件照；未标记时按比例启发式兜底。"""
    if not resume or not resume.images:
        return None
    if resume.candidate_photo_id:
        for image in resume.images:
            if image.image_id == resume.candidate_photo_id:
                return image
    first_page_images = [image for image in resume.images if image.page_number == 1]
    portrait_images = [
        image
        for image in first_page_images
        if image.width and image.height and 0.5 <= image.width / image.height <= 0.85
    ]
    return portrait_images[0] if portrait_images else resume.images[0]


@router.get("/", response_class=HTMLResponse)
def portal(request: Request):
    return templates.TemplateResponse(request, "portal.html", {})


@router.get("/meetings", response_class=HTMLResponse)
@router.get("/meetings/new", response_class=HTMLResponse)
def index(
    request: Request,
    raw_text: str = "",
    candidate_name: str = "",
    position: str = "",
    interviewer_names: str = "",
    error: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "raw_text": raw_text,
            "candidate_name": candidate_name,
            "position": position,
            "interviewer_names": interviewer_names,
            "error": error,
        },
    )


@router.post("/interviews")
@router.post("/meetings/interviews")
async def create_interview_from_page(
    request: Request,
    raw_text: str = Form(...),
    candidate_name: str = Form(""),
    position: str = Form(""),
    interviewer_names: str = Form(""),
    resume: UploadFile | None = File(None),
    destination: str = Form("schedule"),
    confirmation_token: str = Form(""),
    action: str = Form("save"),
    reviewed_subject: str = Form(""),
    reviewed_kind: str = Form(""),
    reviewed_start: str = Form(""),
    reviewed_end: str = Form(""),
    reviewed_platform: str = Form(""),
    reviewed_meeting_url: str = Form(""),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    resume_service: ResumeParserService = Depends(get_resume_parser_service),
    my_interview_service: MyInterviewService = Depends(get_my_interview_service),
):
    resume_id = None
    parsed_resume = None
    warning_token = ""
    reviewed_fields = None
    try:
        dto = MeetingEntryCreateDTO(
            raw_text=raw_text,
            candidate_name=candidate_name or None,
            position=position or None,
            interviewer_names=interviewer_names,
        )
        preview_entry = schedule_service.meeting_parser.parse(dto)
        preview_entry.start_time = preview_entry.start_time.astimezone(ZoneInfo("Asia/Shanghai"))
        preview_entry.end_time = preview_entry.end_time.astimezone(ZoneInfo("Asia/Shanghai"))
        if action == "preview":
            return templates.TemplateResponse(request, "index.html", {
                "raw_text": raw_text, "candidate_name": candidate_name,
                "position": position, "interviewer_names": interviewer_names,
                "parsed_preview": preview_entry, "error": None,
            })
        if reviewed_subject or reviewed_start or reviewed_end:
            reviewed_fields = {
                "subject": reviewed_subject.strip(), "kind": reviewed_kind,
                "start_time": datetime.fromisoformat(reviewed_start),
                "end_time": datetime.fromisoformat(reviewed_end),
                "platform": reviewed_platform.strip() or preview_entry.platform,
                "meeting_url": reviewed_meeting_url.strip() or None,
            }
            preview_entry = type(preview_entry).model_validate({
                **preview_entry.model_dump(), **reviewed_fields,
            })
        warning_token = sha256(repr((
            raw_text, preview_entry.kind, preview_entry.subject,
            preview_entry.start_time.isoformat(), preview_entry.end_time.isoformat(),
            preview_entry.platform, str(preview_entry.meeting_url or ""),
        )).encode("utf-8")).hexdigest()
        if destination != "mine" and confirmation_token != warning_token:
            duplicate = schedule_service.schedule_mapper.find_duplicate(preview_entry)
            warnings = [] if duplicate else schedule_service.non_working_warnings(preview_entry)
            if warnings:
                return templates.TemplateResponse(
                    request,
                    "index.html",
                    {
                        "raw_text": raw_text,
                        "candidate_name": candidate_name,
                        "position": position,
                        "interviewer_names": interviewer_names,
                        "error": None,
                        "warnings": warnings,
                        "confirmation_token": warning_token,
                        "parsed_preview": preview_entry,
                    },
                    status_code=409,
                )
        if resume and resume.filename:
            parsed_resume = await resume_service.parse_upload(resume)
            resume_id = parsed_resume.id
        dto.resume_id = resume_id
        if destination == "mine":
            entry = my_interview_service.create_from_invitation(dto, uploaded_resume=parsed_resume)
        else:
            entry = schedule_service.create_from_invitation(
                dto, confirm_non_working=confirmation_token == warning_token,
                reviewed_fields=reviewed_fields,
            )
    except ScheduleConflictWarning as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "raw_text": raw_text,
                "candidate_name": candidate_name,
                "position": position,
                "interviewer_names": interviewer_names,
                "error": None,
                "warnings": exc.warnings,
                "confirmation_token": warning_token,
                "parsed_preview": preview_entry,
            },
            status_code=409,
        )
    except (MeetingParseError, ResumeParseError, MyResumeNotFoundError, ValueError, ValidationError) as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "raw_text": raw_text,
                "candidate_name": candidate_name,
                "position": position,
                "interviewer_names": interviewer_names,
                "error": str(exc),
            },
            status_code=422,
        )

    target_date = entry.start_time.date().isoformat()
    redirect_url = "/my-interviews" if destination == "mine" else "/meetings/schedule"
    return RedirectResponse(url=f"{redirect_url}?date={target_date}", status_code=303)


@router.get("/schedule", response_class=HTMLResponse)
@router.get("/meetings/schedule", response_class=HTMLResponse)
def schedule(
    request: Request,
    date: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    overview: str | None = None,
    service: ScheduleService = Depends(get_schedule_service),
    calendar_service: EnterpriseCalendarService = Depends(get_enterprise_calendar_service),
):
    calendar_settings = calendar_service.get_settings()
    display_zone = ZoneInfo(calendar_settings.timezone)
    try:
        selected_date = date_type.fromisoformat(date) if date else datetime.now(display_zone).date()
    except ValueError:
        selected_date = datetime.now(display_zone).date()

    workday = calendar_settings.for_date(selected_date)
    start_time = start_time or workday.start.strftime("%H:%M")
    end_time = end_time or workday.end.strftime("%H:%M")

    try:
        start_parts = [int(value) for value in start_time.split(":")]
        end_parts = [int(value) for value in end_time.split(":")]
    except ValueError:
        start_parts, end_parts = [9, 0], [19, 0]
    start_hour = start_parts[0] + start_parts[1] / 60 if len(start_parts) == 2 else 9
    end_hour = end_parts[0] + end_parts[1] / 60 if len(end_parts) == 2 else 19
    start_hour = max(0.0, min(start_hour, 23.5))
    end_hour = max(start_hour + 0.5, min(end_hour, 24.0))

    entries = [entry for entry in service.list_non_personal() if entry.start_time.astimezone(display_zone).date() == selected_date]
    current_now = datetime.now(display_zone)
    entry_views = [_build_entry_view(entry, current_now, display_zone) for entry in entries]
    _assign_entry_columns(entry_views)

    overview_mode = overview if overview in ("expired", "today") else None
    overview_groups = service.list_overview(current_now)
    overview_finished = [_build_entry_view(entry, current_now, display_zone) for entry in overview_groups["finished"]]
    overview_today = [_build_entry_view(entry, current_now, display_zone) for entry in overview_groups["today"]]
    hour_height = 156
    time_labels = [
        {"text": f"{int(minutes // 60):02d}:{int(minutes % 60):02d}", "top": (minutes - start_hour * 60) / 60 * hour_height}
        for minutes in range(int(start_hour * 60), int(end_hour * 60) + 1, 30)
    ]

    current_minutes = current_now.hour * 60 + current_now.minute
    show_now_line = selected_date == current_now.date() and start_hour * 60 <= current_minutes <= end_hour * 60
    now_top = (current_minutes - start_hour * 60) / 60 * hour_height

    available_dates = {entry.start_time.astimezone(display_zone).date() for entry in service.list_non_personal()}
    available_dates.add(selected_date)
    available_dates.add(current_now.date())
    date_options = []
    for day in sorted(available_dates):
        date_options.append({"date": day.isoformat(), "label": day.strftime("%m-%d")})

    return templates.TemplateResponse(
        request,
        "schedule.html",
        {
            "selected_date": selected_date.isoformat(),
            "selected_weekday": WEEKDAY_NAMES[selected_date.weekday()],
            "entries": entry_views,
            "date_options": date_options,
            "time_options": _time_options(),
            "start_time": f"{int(start_hour):02d}:{'00' if start_hour % 1 == 0 else '30'}",
            "end_time": f"{int(end_hour):02d}:{'00' if end_hour % 1 == 0 else '30'}",
            "start_hour": start_hour,
            "end_hour": end_hour,
            "time_labels": time_labels,
            "grid_height": int((end_hour - start_hour) * hour_height),
            "hour_height": hour_height,
            "show_lunch": start_hour < 13 and end_hour > 12,
            "show_tea_break": start_hour < 16.5 and end_hour > 16,
            "shaded_blocks": calendar_service.shaded_blocks(selected_date, int(start_hour * 60), int(end_hour * 60)),
            "calendar_timezone": calendar_settings.timezone,
            "show_now_line": show_now_line,
            "now_time": current_now.strftime("%H:%M"),
            "now_top": now_top,
            "overview": overview_mode,
            "overview_finished": overview_finished,
            "overview_today": overview_today,
        },
    )


@router.get("/meetings/settings", response_class=HTMLResponse)
def enterprise_calendar_settings_page(
    request: Request,
    saved: bool = False,
    calendar_service: EnterpriseCalendarService = Depends(get_enterprise_calendar_service),
):
    return templates.TemplateResponse(request, "enterprise_settings.html", {
        "settings": calendar_service.get_settings(),
        "weekday_names": WEEKDAY_NAMES,
        "saved": saved,
        "error": None,
    })


@router.post("/meetings/settings", response_class=HTMLResponse)
async def update_enterprise_calendar_settings(
    request: Request,
    calendar_service: EnterpriseCalendarService = Depends(get_enterprise_calendar_service),
):
    form = await request.form()
    days: dict[int, dict[str, Any]] = {}
    for weekday in range(7):
        names = form.getlist(f"break_name_{weekday}")
        starts = form.getlist(f"break_start_{weekday}")
        ends = form.getlist(f"break_end_{weekday}")
        enabled_values = form.getlist(f"break_enabled_{weekday}") or ["on"] * len(names)
        breaks = [
            {"name": name.strip(), "start": start, "end": end, "enabled": enabled == "on"}
            for name, start, end, enabled in zip(names, starts, ends, enabled_values)
            if name.strip() or start or end
        ]
        days[weekday] = {
            "enabled": form.get(f"enabled_{weekday}") == "on",
            "start": form.get(f"start_{weekday}"),
            "end": form.get(f"end_{weekday}"),
            "breaks": breaks,
        }
    try:
        settings = EnterpriseCalendarSettings.model_validate({
            "timezone": form.get("timezone"), "days": days,
        })
    except ValidationError as exc:
        message = "; ".join(error["msg"] for error in exc.errors()[:3])
        return templates.TemplateResponse(request, "enterprise_settings.html", {
            "settings": calendar_service.get_settings(),
            "weekday_names": WEEKDAY_NAMES,
            "saved": False,
            "error": message,
        }, status_code=422)
    calendar_service.save_settings(settings)
    return RedirectResponse(url="/meetings/settings?saved=true", status_code=303)



def _build_my_interviews_context(
    date: str | None,
    start_time: str,
    end_time: str,
    my_service: MyInterviewService,
) -> dict[str, Any]:
    try:
        selected_date = date_type.fromisoformat(date) if date else datetime.now(ZoneInfo("Asia/Shanghai")).date()
    except ValueError:
        selected_date = datetime.now(ZoneInfo("Asia/Shanghai")).date()

    start_parts = [int(value) for value in start_time.split(":")]
    end_parts = [int(value) for value in end_time.split(":")]
    start_hour = start_parts[0] + start_parts[1] / 60 if len(start_parts) == 2 else 9
    end_hour = end_parts[0] + end_parts[1] / 60 if len(end_parts) == 2 else 19
    start_hour = max(6.0, min(start_hour, 21.5))
    end_hour = max(start_hour + 0.5, min(end_hour, 22.0))

    current_now = datetime.now(ZoneInfo("Asia/Shanghai"))
    entries = [entry for entry in my_service.list_entries() if entry.start_time.date() == selected_date]
    entry_views = [_build_entry_view(entry, current_now) for entry in entries]
    _assign_entry_columns(entry_views)
    hour_height = 156
    time_labels = [
        {
            "text": f"{int(minutes // 60):02d}:{int(minutes % 60):02d}",
            "top": (minutes - start_hour * 60) / 60 * hour_height,
            "minutes": minutes,
        }
        for minutes in range(int(start_hour * 60), int(end_hour * 60) + 1, 30)
    ]
    current_minutes = current_now.hour * 60 + current_now.minute
    show_now_line = selected_date == current_now.date() and start_hour * 60 <= current_minutes <= end_hour * 60

    today = current_now.date()
    yesterday = selected_date - timedelta(days=1)
    tomorrow = selected_date + timedelta(days=1)

    def date_option(day: date_type) -> dict[str, str]:
        if day == today - timedelta(days=1):
            label = "\u6628\u5929"
        elif day == today:
            label = "\u4eca\u5929"
        elif day == today + timedelta(days=1):
            label = "\u660e\u5929"
        else:
            label = day.strftime("%m-%d")
        return {"date": day.isoformat(), "label": label}

    all_views = [_build_entry_view(entry, current_now) for entry in my_service.list_entries()]
    finished_entries = [entry for entry in all_views if entry["status"] == "finished"]
    today_entries = [
        entry for entry in all_views
        if entry["status"] != "finished" and entry["start_time"].date() == today
    ]
    my_resume = my_service.get_resume()
    my_photo = _select_candidate_photo(my_resume)

    return {
        "selected_date": selected_date.isoformat(),
        "selected_weekday": WEEKDAY_NAMES[selected_date.weekday()],
        "date_options": [date_option(yesterday), date_option(selected_date), date_option(tomorrow)],
        "prev_date": yesterday.isoformat(),
        "next_date": tomorrow.isoformat(),
        "entries": entry_views,
        "finished_entries": finished_entries,
        "today_entries": today_entries,
        "my_resume": my_resume,
        "my_photo": my_photo,
        "time_options": _time_options(),
        "start_time": f"{int(start_hour):02d}:{'00' if start_hour % 1 == 0 else '30'}",
        "end_time": f"{int(end_hour):02d}:{'00' if end_hour % 1 == 0 else '30'}",
        "start_hour": start_hour,
        "end_hour": end_hour,
        "time_labels": time_labels,
        "grid_height": int((end_hour - start_hour) * hour_height),
        "hour_height": hour_height,
        "show_lunch": start_hour < 13 and end_hour > 12,
        "show_tea_break": start_hour < 16.5 and end_hour > 16,
        "show_now_line": show_now_line,
        "now_time": current_now.strftime("%H:%M"),
        "now_minutes": current_minutes,
    }


@router.get("/my-interviews", response_class=HTMLResponse)
def my_interviews(
    request: Request,
    date: str | None = None,
    start_time: str = "09:00",
    end_time: str = "19:00",
    fragment: bool = False,
    service: ScheduleService = Depends(get_schedule_service),
    my_service: MyInterviewService = Depends(get_my_interview_service),
    resume_service: ResumeParserService = Depends(get_resume_parser_service),
):
    ctx = _build_my_interviews_context(date, start_time, end_time, my_service)
    if fragment:
        return templates.TemplateResponse(request, "my_interviews_body.html", ctx)
    return templates.TemplateResponse(request, "my_interviews.html", ctx)


@router.post("/my/resume", response_class=HTMLResponse)
async def upload_my_resume(
    request: Request,
    resume: UploadFile = File(...),
    my_service: MyInterviewService = Depends(get_my_interview_service),
    resume_service: ResumeParserService = Depends(get_resume_parser_service),
):
    try:
        parsed_resume = await resume_service.parse_upload(resume)
        my_service.save_resume(parsed_resume)
    except ResumeParseError as exc:
        return templates.TemplateResponse(
            request,
            "my_interviews.html",
            {
                "resume_error": str(exc),
                "my_resume": my_service.get_resume(),
                "my_photo": None,
                "selected_date": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
                "selected_weekday": WEEKDAY_NAMES[datetime.now(ZoneInfo("Asia/Shanghai")).weekday()],
                "date_options": [],
                "prev_date": None,
                "next_date": None,
                "entries": [],
                "finished_entries": [],
                "today_entries": [],
                "time_options": _time_options(),
                "start_time": "09:00",
                "end_time": "19:00",
                "start_hour": 9,
                "end_hour": 19,
                "time_labels": [],
                "grid_height": 1560,
                "hour_height": 156,
                "show_lunch": True,
                "show_tea_break": True,
                "show_now_line": False,
                "now_time": "",
                "now_top": 0,
            },
            status_code=422,
        )
    return RedirectResponse(url="/my-interviews", status_code=303)

@router.get("/interviews/{entry_id}", response_class=HTMLResponse)
def interview_detail(
    entry_id: str,
    request: Request,
    service: ScheduleService = Depends(get_schedule_service),
    resume_service: ResumeParserService = Depends(get_resume_parser_service),
):
    try:
        entry = service.get_entry(entry_id)
    except Exception:
        return RedirectResponse(url="/meetings/schedule", status_code=303)
    if entry.source == "personal":
        return RedirectResponse(url=f"/my-schedule/events/{entry.id}", status_code=302)
    resume = resume_service.get_resume(entry.resume_id) if entry.kind == "interview" and entry.resume_id else None
    candidate_photo = _select_candidate_photo(resume)
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"entry": entry, "resume": resume, "candidate_photo": candidate_photo, "display_platform": MeetingParserService.display_platform(entry), "resume_error": None},
    )


@router.post("/interviews/{entry_id}/resume")
async def upload_interview_resume(
    entry_id: str,
    request: Request,
    resume: UploadFile = File(...),
    schedule_service: ScheduleService = Depends(get_schedule_service),
    resume_service: ResumeParserService = Depends(get_resume_parser_service),
):
    try:
        entry = schedule_service.get_entry(entry_id)
    except EntryNotFoundError:
        return RedirectResponse(url="/schedule", status_code=303)

    try:
        parsed_resume = await resume_service.parse_upload(resume)
    except ResumeParseError as exc:
        return templates.TemplateResponse(
            request,
            "detail.html",
            {
                "entry": entry,
                "resume": None,
                "candidate_photo": None,
                "resume_error": str(exc),
            },
            status_code=422,
        )

    schedule_service.attach_resume(entry.id, parsed_resume.id)
    return RedirectResponse(url=f"/interviews/{entry.id}", status_code=303)
