from pathlib import Path

import logging
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.controller import (
    admin_dashboard_controller,
    performance_controller,
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
from app.core.performance import RequestTimings, node_for_path, request_timings
from app.mapper.postgres_auth_mapper import PostgresAuthMapper
from app.service.auth_service import AuthService
from app.service.performance_service import PerformanceService

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
    performance = PerformanceService(Path(settings.performance_db_path),
                                     enabled=public and settings.performance_enabled)

    @asynccontextmanager
    async def lifespan(_application):
        performance.start()
        try:
            yield
        finally:
            performance.stop()

    application = FastAPI(
        title="Awesome Interview" if public else "会议日程规划器",
        version="0.1.0",
        docs_url=None if public else "/docs",
        redoc_url=None if public else "/redoc",
        openapi_url=None if public else "/openapi.json",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.performance = performance
    application.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @application.middleware("http")
    async def measure_personal_requests(request: Request, call_next):
        node = node_for_path(request.url.path, request.method)
        if node is None:
            return await call_next(request)
        started = perf_counter()
        timings = RequestTimings()
        token = request_timings.set(timings)
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            elapsed_ms = (perf_counter() - started) * 1000
            legacy_metric = "experience" if request.url.path.startswith("/my-schedule/experiences") else "personal"
            response.headers["Server-Timing"] = ", ".join(
                [f"app;dur={elapsed_ms:.1f}", f"{legacy_metric};dur={elapsed_ms:.1f}"] +
                [f"{name};dur={duration:.1f}" for name, duration in timings.values.items()])
            return response
        finally:
            elapsed_ms = (perf_counter() - started) * 1000
            performance.record(node, "server", "request", elapsed_ms, status)
            for name, duration in timings.values.items():
                performance.record(node, "server", name, duration, status)
            request_timings.reset(token)
            if elapsed_ms >= 500:
                logger.warning("Slow request node=%s method=%s status=%s duration_ms=%.1f",
                               node, request.method, status, elapsed_ms)
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
        application.include_router(admin_dashboard_controller.router,
                                   dependencies=[Depends(require_current_user)])
        application.include_router(performance_controller.router,
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
