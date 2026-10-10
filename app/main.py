from pathlib import Path

import logging
from time import perf_counter

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.controller import (
    account_profile_controller,
    ai_interview_controller,
    auth_controller,
    page_controller,
    personal_resume_controller,
    interview_experience_controller,
    mobile_api_controller,
    resume_controller,
    schedule_controller,
    personal_schedule_controller,
    public_page_controller,
)
from app.core.auth_guard import AuthRequired, InvalidCsrf, require_current_user
from app.core.config import Settings, get_settings
from app.mapper.postgres_auth_mapper import PostgresAuthMapper
from app.service.auth_service import AuthService

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, auth_service: AuthService | None = None) -> FastAPI:
    settings = settings or get_settings()
    public = settings.app_mode == "public_personal"
    if public:
        if settings.storage_backend == "memory":
            raise RuntimeError("公开模式必须使用持久化存储")
        if not settings.public_base_url.startswith("https://"):
            raise RuntimeError("公开模式必须配置 HTTPS PUBLIC_BASE_URL")
        if (settings.registration_mode != "closed" and settings.email_verification_required
                and (not settings.smtp_host or not settings.smtp_from)):
            raise RuntimeError("开放注册前必须配置 SMTP_HOST 和 SMTP_FROM")
        if settings.registration_mode == "invite" and not settings.registration_invite_code:
            raise RuntimeError("邀请码注册必须配置 REGISTRATION_INVITE_CODE")
    application = FastAPI(
        title="Awesome Interview" if public else "会议日程规划器",
        version="0.1.0",
        docs_url=None if public else "/docs",
        redoc_url=None if public else "/redoc",
        openapi_url=None if public else "/openapi.json",
    )
    application.state.settings = settings
    application.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @application.middleware("http")
    async def measure_personal_requests(request: Request, call_next):
        if not request.url.path.startswith("/my-schedule"):
            return await call_next(request)
        started = perf_counter()
        response = await call_next(request)
        elapsed_ms = (perf_counter() - started) * 1000
        metric = "experience" if request.url.path.startswith("/my-schedule/experiences") else "personal"
        response.headers["Server-Timing"] = f"{metric};dur={elapsed_ms:.1f}"
        if elapsed_ms >= 500:
            logger.warning("Slow personal request path=%s method=%s status=%s duration_ms=%.1f",
                           request.url.path, request.method, response.status_code, elapsed_ms)
        return response
    if public:
        application.state.auth_service = auth_service or AuthService(PostgresAuthMapper(settings), settings)

        @application.middleware("http")
        async def prevent_private_cache(request: Request, call_next):
            response = await call_next(request)
            if not request.url.path.startswith("/static/"):
                response.headers["Cache-Control"] = "no-store"
                response.headers["Referrer-Policy"] = "no-referrer"
            return response

        @application.exception_handler(AuthRequired)
        async def handle_auth_required(request: Request, exc: AuthRequired):
            if request.method == "GET" and request.url.path.startswith("/my-schedule"):
                return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=303)
            return JSONResponse({"detail": "请先登录"}, status_code=401)

        @application.exception_handler(InvalidCsrf)
        async def handle_invalid_csrf(request: Request, exc: InvalidCsrf):
            return JSONResponse({"detail": "表单已过期，请刷新重试"}, status_code=403)

        application.include_router(public_page_controller.router)
        application.include_router(auth_controller.router)
        application.include_router(personal_schedule_controller.router,
                                   dependencies=[Depends(require_current_user)])
        application.include_router(personal_resume_controller.router,
                                   dependencies=[Depends(require_current_user)])
        application.include_router(interview_experience_controller.router,
                                   dependencies=[Depends(require_current_user)])
        application.include_router(account_profile_controller.router,
                                   dependencies=[Depends(require_current_user)])
        application.include_router(mobile_api_controller.router,
                                   dependencies=[Depends(require_current_user)])
    else:
        application.include_router(page_controller.router)
        application.include_router(schedule_controller.router)
        application.include_router(resume_controller.router)
        application.include_router(ai_interview_controller.router)
        application.include_router(personal_schedule_controller.router)
        application.include_router(interview_experience_controller.router)
    return application


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8291, reload=True)
