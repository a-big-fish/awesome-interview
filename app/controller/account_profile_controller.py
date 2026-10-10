"""Personal account display settings."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.controller.page_controller import templates


router = APIRouter(prefix="/my-schedule/profile", tags=["account-profile"])


@router.get("", response_class=HTMLResponse)
def profile_page(request: Request, saved: bool = False):
    return templates.TemplateResponse(request, "account_profile.html", {
        "user": request.state.user, "saved": saved, "error": "",
    })


@router.post("", response_class=HTMLResponse)
async def update_profile(request: Request):
    form = await request.form()
    try:
        request.app.state.auth_service.update_display_name(
            request.state.user.id, str(form.get("display_name", "")),
        )
    except ValueError as exc:
        return templates.TemplateResponse(request, "account_profile.html", {
            "user": request.state.user, "saved": False, "error": str(exc),
            "entered_name": str(form.get("display_name", "")),
        }, status_code=422)
    return RedirectResponse("/my-schedule/profile?saved=1", status_code=303)
