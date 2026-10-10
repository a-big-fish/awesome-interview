"""Single-entry public portal; enterprise pages are not registered here."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.controller.page_controller import templates
from app.core.auth_guard import SESSION_COOKIE


router = APIRouter(tags=["public-pages"])


@router.get("/", response_class=HTMLResponse)
def public_home(request: Request):
    if request.app.state.auth_service.authenticate(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/my-schedule/experiences/plaza", status_code=303)
    return templates.TemplateResponse(request, "public_portal.html", {})
