"""Administrator-only, aggregate-only site dashboard."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.controller.page_controller import templates
from app.core.dependencies import get_interview_experience_mapper
from app.mapper.base_interview_experience_mapper import BaseInterviewExperienceMapper
from app.service.admin_dashboard_service import build_admin_dashboard


router = APIRouter(prefix="/my-schedule/admin", tags=["admin"])


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request,
              experience_mapper: BaseInterviewExperienceMapper = Depends(get_interview_experience_mapper)):
    """Show counts without exposing account or private note details."""
    if not request.state.user.is_admin:
        raise HTTPException(status_code=403, detail="无权访问数据看板")
    stats = build_admin_dashboard(request.app.state.auth_service.mapper, experience_mapper)
    return templates.TemplateResponse(request, "admin_dashboard.html", {"stats": stats})
