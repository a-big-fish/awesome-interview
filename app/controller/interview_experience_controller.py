"""Server-rendered interview notes, editing forms, and exports."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import ValidationError

from app.controller.page_controller import templates
from app.core.dependencies import get_interview_experience_service
from app.model.auth import AuthUser
from app.model.interview_experience import CATEGORY_LABELS
from app.service.interview_experience_export import (
    EXPORT_STYLES, effective_total_minutes, export_markdown, export_pdf,
    export_sections, section_heading,
)
from app.service.interview_experience_service import InterviewExperienceService
from app.service.interview_experience_parser import (
    extract_experience_pdf, parse_experience_markdown, parse_experience_text,
)


router = APIRouter(prefix="/my-schedule/experiences", tags=["interview-experiences"])


def _required(service: InterviewExperienceService, experience_id: str):
    experience = service.get_experience(experience_id)
    if not experience:
        raise HTTPException(status_code=404, detail="面经不存在")
    return experience


def _author_label(user: AuthUser | None, owner_id: str) -> str:
    """Show a stable public author label without exposing login email."""
    if user and user.display_name:
        return user.display_name
    if user and user.email:
        return f"热心用户_{user.email.split('@', 1)[0][:3]}"
    if user and user.username:
        return user.username
    if owner_id == "local":
        return "本地用户"
    return f"用户 #{owner_id.replace('-', '')[:8]}"


def _public_author(request: Request, owner_id: str) -> str:
    auth_service = getattr(request.app.state, "auth_service", None)
    user = auth_service.mapper.get_user(owner_id) if auth_service else None
    return _author_label(user, owner_id)


def _form_value(form, key: str) -> str:
    return str(form.get(key, "")).strip()


def _interviewed_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, ValidationError) as exc:
        raise ValueError("面试时间格式无效") from exc
    return parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai")) if parsed.tzinfo is None else parsed


def _detail_url(service: InterviewExperienceService, experience_id: str) -> str:
    experience = service.get_experience(experience_id)
    event = service.schedule_service.get_event(experience.linked_event_id) if experience and experience.linked_event_id else None
    if event and event.type == "interview":
        return (f"/my-schedule/interviews/{experience.linked_event_id}"
                f"?experience_id={experience_id}&saved=1")
    return f"/my-schedule/experiences/{experience_id}?saved=1"


def _export_style(style: str) -> str:
    if style not in EXPORT_STYLES:
        raise HTTPException(status_code=422, detail="导出样式无效")
    return style


def _export_experience(experience, title: str, hide_company: bool,
                       hide_position: bool, hide_interviewed_at: bool):
    title = title.strip()
    if len(title) > 200:
        raise HTTPException(status_code=422, detail="导出标题不能超过 200 个字符")
    return experience.model_copy(update={
        "title": title or experience.title,
        "company": None if hide_company else experience.company,
        "position": None if hide_position else experience.position,
        "interviewed_at": None if hide_interviewed_at else experience.interviewed_at,
    })


@router.get("", response_class=HTMLResponse)
def experience_list(request: Request,
                    service: InterviewExperienceService = Depends(get_interview_experience_service)):
    items = service.list_experiences()
    event_options = [event for event in service.schedule_service.list_events()
                     if event.type == "interview"]
    return templates.TemplateResponse(request, "interview_experience_list.html", {
        "experiences": items, "event_options": event_options,
        "count_by_id": service.count_questions_by_experience(),
    })


@router.post("", response_class=HTMLResponse)
async def create_experience(request: Request,
                            service: InterviewExperienceService = Depends(get_interview_experience_service)):
    form = await request.form()
    event_id = _form_value(form, "linked_event_id") or None
    try:
        experience = service.create_experience(
            title=_form_value(form, "title"), linked_event_id=event_id,
            company=_form_value(form, "company"), position=_form_value(form, "position"),
            interviewed_at=_interviewed_at(_form_value(form, "interviewed_at")),
            is_public=_form_value(form, "is_public") != "private",
            interview_round=_form_value(form, "interview_round"),
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse(_detail_url(service, experience.id), status_code=303)


@router.get("/plaza", response_class=HTMLResponse)
def experience_plaza(request: Request, company: str = "", order: str = "newest",
                     page: int = 1,
                     service: InterviewExperienceService = Depends(get_interview_experience_service)):
    order = order if order in {"newest", "oldest"} else "newest"
    items, total = service.list_plaza(company=company.strip()[:200], order=order,
                                      page=max(1, page))
    auth_service = getattr(request.app.state, "auth_service", None)
    owner_ids = list({row["experience"].owner_id for row in items})
    authors = auth_service.mapper.get_users(owner_ids) if auth_service else {}
    for row in items:
        owner_id = row["experience"].owner_id
        row["author"] = _author_label(authors.get(owner_id), owner_id)
    return templates.TemplateResponse(request, "interview_experience_plaza.html", {
        "items": items, "total": total, "company": company, "order": order,
        "page": max(1, page), "page_size": 20,
    })


@router.get("/plaza/{experience_id}", response_class=HTMLResponse)
def experience_plaza_detail(experience_id: str, request: Request,
                            service: InterviewExperienceService = Depends(get_interview_experience_service)):
    result = service.get_public_experience(experience_id)
    if not result:
        raise HTTPException(status_code=404, detail="面经不存在")
    experience, questions = result
    numbered = service.number_questions(questions)
    return templates.TemplateResponse(request, "interview_experience_plaza_detail.html", {
        "experience": experience,
        "sections": {key: service.tree_rows(numbered, key) for key in CATEGORY_LABELS},
        "category_labels": CATEGORY_LABELS, "author": _public_author(request, experience.owner_id),
    })


@router.post("/{experience_id}/visibility")
async def update_experience_visibility(experience_id: str, request: Request,
                                       service: InterviewExperienceService = Depends(get_interview_experience_service)):
    form = await request.form()
    try:
        service.set_visibility(experience_id, _form_value(form, "is_public") == "public")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse("/my-schedule/experiences", status_code=303)


@router.get("/{experience_id}", response_class=HTMLResponse)
def experience_detail(experience_id: str, request: Request, category: str = "all",
                      saved: int = 0,
                      service: InterviewExperienceService = Depends(get_interview_experience_service)):
    return _render_experience_editor(experience_id, request, category, saved, service, "manual")


@router.get("/{experience_id}/write", response_class=HTMLResponse)
def experience_write(experience_id: str, request: Request,
                     service: InterviewExperienceService = Depends(get_interview_experience_service)):
    return _render_experience_editor(experience_id, request, "all", 0, service, "write")


@router.get("/{experience_id}/import", response_class=HTMLResponse)
def experience_import(experience_id: str, request: Request,
                      service: InterviewExperienceService = Depends(get_interview_experience_service)):
    return _render_experience_editor(experience_id, request, "all", 0, service, "import")


def _render_experience_editor(experience_id: str, request: Request, category: str,
                              saved: int, service: InterviewExperienceService,
                              editor_mode: str):
    experience = _required(service, experience_id)
    linked_event = service.schedule_service.get_event(experience.linked_event_id) if experience.linked_event_id else None
    if linked_event and linked_event.type != "interview":
        linked_event = None
    if category not in {"all", "feeling", *CATEGORY_LABELS}:
        category = "all"
    rows = service.numbered_questions(experience_id)
    return templates.TemplateResponse(request, "interview_experience_detail.html", {
        "experience": experience,
        "linked_event": linked_event,
        "linked_event_missing": bool(experience.linked_event_id and not linked_event),
        "question_rows": rows,
        "visible_rows": rows if category == "all" else service.tree_rows(rows, category) if category != "feeling" else [],
        "draft_seed": {"version": experience.updated_at.isoformat(),
                       "questions": [row["question"].model_dump(mode="json") for row in rows],
                       "category_minutes": experience.category_minutes,
                       "total_minutes": experience.total_minutes,
                       "feeling": experience.feeling or "",
                       "raw_text_draft": experience.raw_text_draft},
        "category": category, "category_labels": CATEGORY_LABELS, "saved": saved,
        "editor_mode": editor_mode,
        "event_options": [event for event in service.schedule_service.list_events()
                          if event.type == "interview"],
        "detail_url": f"/my-schedule/experiences/{experience_id}",
    })


@router.post("/{experience_id}/draft", response_class=JSONResponse)
async def save_experience_draft(experience_id: str, request: Request,
                                service: InterviewExperienceService = Depends(get_interview_experience_service)):
    form = await request.form()
    try:
        payload = json.loads(str(form.get("payload", "")))
        if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
            raise ValueError("草稿格式无效")
        version = datetime.fromisoformat(str(payload.get("version", "")))
        experience, questions = service.save_draft(
            experience_id, version, payload["questions"],
            payload.get("category_minutes"), payload.get("total_minutes"),
            payload.get("feeling"), payload.get("raw_text_draft"))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, TypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"version": experience.updated_at.isoformat(),
            "questions": [item.model_dump(mode="json") for item in questions],
            "category_minutes": experience.category_minutes,
            "total_minutes": experience.total_minutes,
            "feeling": experience.feeling or "",
            "raw_text_draft": experience.raw_text_draft}


@router.post("/{experience_id}/parse", response_class=JSONResponse)
async def preview_text_parse(experience_id: str, request: Request,
                             service: InterviewExperienceService = Depends(get_interview_experience_service)):
    _required(service, experience_id)
    form = await request.form()
    try:
        return parse_experience_text(str(form.get("source", "")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{experience_id}/parse-file", response_class=JSONResponse)
async def preview_document_parse(experience_id: str, request: Request,
                                 service: InterviewExperienceService = Depends(get_interview_experience_service)):
    """Preview a Markdown or text-layer PDF without saving imported questions."""
    _required(service, experience_id)
    form = await request.form()
    upload = form.get("file")
    filename = str(getattr(upload, "filename", "") or "").lower()
    if not filename.endswith((".md", ".markdown", ".pdf")):
        raise HTTPException(status_code=422, detail="仅支持 Markdown (.md) 或 PDF 文件")
    content = await upload.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="文件不能超过 5 MB")
    try:
        if filename.endswith(".pdf"):
            source = extract_experience_pdf(content)
        else:
            source = content.decode("utf-8-sig")
        result = parse_experience_markdown(source)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Markdown 文件需使用 UTF-8 编码") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["source_text"] = source
    return result


@router.post("/{experience_id}/edit")
async def edit_experience(experience_id: str, request: Request,
                          service: InterviewExperienceService = Depends(get_interview_experience_service)):
    form = await request.form()
    try:
        service.update_experience(
            experience_id, title=_form_value(form, "title"),
            linked_event_id=_form_value(form, "linked_event_id") or None,
            company=_form_value(form, "company"), position=_form_value(form, "position"),
            interviewed_at=_interviewed_at(_form_value(form, "interviewed_at")),
            is_public=_form_value(form, "is_public") == "public",
            interview_round=_form_value(form, "interview_round"),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse("/my-schedule/experiences", status_code=303)


@router.post("/{experience_id}/delete")
def delete_experience(experience_id: str,
                      service: InterviewExperienceService = Depends(get_interview_experience_service)):
    if not service.delete_experience(experience_id):
        raise HTTPException(status_code=404, detail="面经不存在")
    return RedirectResponse("/my-schedule/experiences", status_code=303)


@router.post("/{experience_id}/questions")
async def add_question(experience_id: str, request: Request,
                       service: InterviewExperienceService = Depends(get_interview_experience_service)):
    form = await request.form()
    try:
        service.add_question(
            experience_id, _form_value(form, "question_text"),
            _form_value(form, "category"),
            _form_value(form, "parent_question_id") or None,
            _form_value(form, "on_site_answer"),
            _form_value(form, "review_answer"),
            _form_value(form, "interviewer_answer"),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse(_detail_url(service, experience_id), status_code=303)


@router.post("/{experience_id}/questions/{question_id}/edit")
async def edit_question(experience_id: str, question_id: str, request: Request,
                        service: InterviewExperienceService = Depends(get_interview_experience_service)):
    form = await request.form()
    try:
        service.update_question(
            experience_id, question_id, question_text=_form_value(form, "question_text"),
            category=_form_value(form, "category"),
            on_site_answer=_form_value(form, "on_site_answer"),
            review_answer=_form_value(form, "review_answer"),
            interviewer_answer=_form_value(form, "interviewer_answer"),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse(_detail_url(service, experience_id), status_code=303)


@router.post("/{experience_id}/questions/{question_id}/delete")
def delete_question(experience_id: str, question_id: str,
                    service: InterviewExperienceService = Depends(get_interview_experience_service)):
    try:
        service.delete_question(experience_id, question_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse(_detail_url(service, experience_id), status_code=303)


@router.post("/{experience_id}/questions/{question_id}/move")
async def move_question(experience_id: str, question_id: str, request: Request,
                        service: InterviewExperienceService = Depends(get_interview_experience_service)):
    form = await request.form()
    try:
        service.move_question(experience_id, question_id, _form_value(form, "direction"))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse(_detail_url(service, experience_id), status_code=303)


@router.get("/{experience_id}/export", response_class=HTMLResponse)
def export_preview(experience_id: str, request: Request, style: str = "lines", title: str = "",
                   hide_company: bool = False, hide_position: bool = False,
                   hide_interviewed_at: bool = False, hide_on_site_answer: bool = False,
                   hide_review_answer: bool = False, hide_interviewer_answer: bool = False,
                   service: InterviewExperienceService = Depends(get_interview_experience_service)):
    source_experience = _required(service, experience_id)
    experience = _export_experience(source_experience, title, hide_company, hide_position, hide_interviewed_at)
    style = _export_style(style)
    rows = service.numbered_questions(experience_id)
    return templates.TemplateResponse(request, "interview_experience_export.html", {
        "experience": experience, "source_experience": source_experience, "style": style,
        "sections": export_sections(rows, style), "export_title": title,
        "hide_company": hide_company, "hide_position": hide_position,
        "hide_interviewed_at": hide_interviewed_at,
        "hide_on_site_answer": hide_on_site_answer,
        "hide_review_answer": hide_review_answer,
        "hide_interviewer_answer": hide_interviewer_answer,
        "total_minutes": effective_total_minutes(experience),
        "section_heading": section_heading,
        "category_labels": CATEGORY_LABELS,
    })


@router.get("/{experience_id}/export.md")
def markdown_export(experience_id: str, style: str = "lines", title: str = "",
                    hide_company: bool = False, hide_position: bool = False,
                    hide_interviewed_at: bool = False, hide_on_site_answer: bool = False,
                    hide_review_answer: bool = False, hide_interviewer_answer: bool = False,
                    service: InterviewExperienceService = Depends(get_interview_experience_service)):
    experience = _export_experience(_required(service, experience_id), title, hide_company,
                                    hide_position, hide_interviewed_at)
    content = export_markdown(experience, service.numbered_questions(experience_id),
                              _export_style(style), hide_on_site_answer=hide_on_site_answer,
                              hide_review_answer=hide_review_answer,
                              hide_interviewer_answer=hide_interviewer_answer)
    return Response(content, media_type="text/markdown; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="interview-experience-{experience.id}.md"',
    })


@router.get("/{experience_id}/export.pdf")
def pdf_export(experience_id: str, style: str = "lines", inline: bool = False, title: str = "",
               hide_company: bool = False, hide_position: bool = False,
               hide_interviewed_at: bool = False, hide_on_site_answer: bool = False,
               hide_review_answer: bool = False, hide_interviewer_answer: bool = False,
               service: InterviewExperienceService = Depends(get_interview_experience_service)):
    experience = _export_experience(_required(service, experience_id), title, hide_company,
                                    hide_position, hide_interviewed_at)
    content = export_pdf(experience, service.numbered_questions(experience_id),
                         _export_style(style), hide_on_site_answer=hide_on_site_answer,
                         hide_review_answer=hide_review_answer,
                         hide_interviewer_answer=hide_interviewer_answer)
    disposition = "inline" if inline else "attachment"
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'{disposition}; filename="interview-experience-{experience.id}.pdf"',
    })
