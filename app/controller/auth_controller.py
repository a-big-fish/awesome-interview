"""Public account pages and cookie lifecycle."""

import hmac
import logging
import secrets
import smtplib
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.controller.page_controller import templates
from app.core.auth_guard import SESSION_COOKIE


router = APIRouter(prefix="/auth", tags=["accounts"])
logger = logging.getLogger(__name__)
GUEST_CSRF_COOKIE = "schedule_guest_csrf"
DEFAULT_AFTER_LOGIN = "/my-schedule/experiences/plaza"


def _safe_next(value: str) -> str:
    return value if value.startswith("/my-schedule") and not value.startswith("//") else DEFAULT_AFTER_LOGIN


def _page(request: Request, mode: str, *, error: str = "", message: str = "",
          next_path: str = DEFAULT_AFTER_LOGIN, reset_token: str = "", status_code: int = 200):
    labels = {
        "login": ("登录", "登录", "/auth/login"),
        "register": ("创建账号", "创建账号", "/auth/register"),
        "forgot": ("找回密码", "发送重置邮件", "/auth/forgot-password"),
        "resend": ("重新发送验证邮件", "发送验证邮件", "/auth/resend-verification"),
        "reset": ("设置新密码", "保存新密码", "/auth/reset-password"),
        "message": ("账号提示", "", ""),
    }
    heading, submit_label, action = labels[mode]
    csrf_token = request.cookies.get(GUEST_CSRF_COOKIE) or secrets.token_urlsafe(32)
    response = templates.TemplateResponse(request, "auth_page.html", {
        "heading": heading, "submit_label": submit_label, "action": action,
        "mode": mode, "error": error, "message": message,
        "csrf_token": csrf_token, "next_path": _safe_next(next_path),
        "reset_token": reset_token,
        "invite_required": request.app.state.settings.registration_mode == "invite",
        "email_verification_required": request.app.state.settings.email_verification_required,
    }, status_code=status_code)
    response.set_cookie(GUEST_CSRF_COOKIE, csrf_token, max_age=3600,
                        httponly=True, secure=request.app.state.settings.auth_cookie_secure,
                        samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return response


async def _checked_form(request: Request):
    form = await request.form()
    submitted = str(form.get("csrf_token", ""))
    cookie = request.cookies.get(GUEST_CSRF_COOKIE, "")
    if not cookie or not hmac.compare_digest(submitted, cookie):
        raise HTTPException(status_code=403, detail="表单已过期，请刷新页面重试")
    return form


def _allowed(request: Request, key: str, limit: int, minutes: int) -> bool:
    return request.app.state.auth_service.limiter.allow(key, limit, timedelta(minutes=minutes))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = DEFAULT_AFTER_LOGIN):
    return _page(request, "login", next_path=next)


@router.post("/login", response_class=HTMLResponse)
async def login(request: Request):
    form = await _checked_form(request)
    identifier = str(form.get("identifier", "")).strip().casefold()
    if not _allowed(request, f"login:{identifier}", 10, 15):
        return _page(request, "login", error="尝试次数过多，请稍后再试", status_code=429)
    result = request.app.state.auth_service.login(identifier, str(form.get("password", "")))
    if not result:
        return _page(request, "login", error="账号或密码不正确，或邮箱尚未验证", status_code=401,
                     next_path=str(form.get("next", "")))
    _, raw_token, _ = result
    response = RedirectResponse(_safe_next(str(form.get("next", ""))), status_code=303)
    response.set_cookie(SESSION_COOKIE, raw_token, max_age=7 * 24 * 3600,
                        httponly=True, secure=request.app.state.settings.auth_cookie_secure,
                        samesite="lax", path="/")
    response.delete_cookie(GUEST_CSRF_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/logout")
async def logout(request: Request):
    raw_token = request.cookies.get(SESSION_COOKIE)
    result = request.app.state.auth_service.authenticate(raw_token)
    if result:
        form = await request.form()
        if not hmac.compare_digest(str(form.get("csrf_token", "")), result[1].csrf_token):
            raise HTTPException(status_code=403, detail="表单已过期，请刷新页面重试")
    request.app.state.auth_service.logout(raw_token)
    response = RedirectResponse("/auth/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if request.app.state.settings.registration_mode == "closed":
        raise HTTPException(status_code=404)
    return _page(request, "register")


@router.post("/register", response_class=HTMLResponse)
async def register(request: Request):
    if request.app.state.settings.registration_mode == "closed":
        raise HTTPException(status_code=404)
    form = await _checked_form(request)
    email = str(form.get("email", ""))
    client_ip = request.client.host if request.client else "unknown"
    if not _allowed(request, f"register-ip:{client_ip}", 30, 60) or not _allowed(
        request, f"register:{email.strip().casefold()}", 5, 60
    ):
        return _page(request, "register", error="尝试次数过多，请稍后再试", status_code=429)
    password = str(form.get("password", ""))
    if password != str(form.get("password_confirm", "")):
        return _page(request, "register", error="两次密码不一致", status_code=422)
    try:
        request.app.state.auth_service.register(email, password, str(form.get("invite_code", "")))
    except ValueError as exc:
        return _page(request, "register", error=str(exc), status_code=422)
    except (OSError, smtplib.SMTPException):
        logger.exception("Registration verification email failed")
        return _page(request, "register", error="邮件发送失败，请稍后通过重新发送验证邮件重试", status_code=503)
    if not request.app.state.settings.email_verification_required:
        return _page(request, "message", message="账号创建成功，请登录。")
    return _page(request, "message", message="如果该邮箱可以注册，请查收验证邮件。")


@router.get("/verify", response_class=HTMLResponse)
def verify_email(request: Request, token: str = ""):
    valid = request.app.state.auth_service.verify_email(token) if token else False
    message = "邮箱验证成功，请登录。" if valid else "验证链接已失效，请重新申请。"
    return _page(request, "message", message=message, status_code=200 if valid else 400)


@router.post("/resend-verification", response_class=HTMLResponse)
async def resend_verification(request: Request):
    if not request.app.state.settings.smtp_host:
        raise HTTPException(status_code=404)
    form = await _checked_form(request)
    email = str(form.get("email", ""))
    if _allowed(request, f"verify:{email.strip().lower()}", 3, 60):
        try:
            request.app.state.auth_service.send_verification(email)
        except (OSError, smtplib.SMTPException):
            logger.exception("Verification email resend failed")
    return _page(request, "message", message="如果账号尚未验证，请查收邮件。")


@router.get("/resend-verification", response_class=HTMLResponse)
def resend_verification_page(request: Request):
    if not request.app.state.settings.smtp_host:
        raise HTTPException(status_code=404)
    return _page(request, "resend")


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_page(request: Request):
    if not request.app.state.settings.smtp_host:
        raise HTTPException(status_code=404)
    return _page(request, "forgot")


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password(request: Request):
    if not request.app.state.settings.smtp_host:
        raise HTTPException(status_code=404)
    form = await _checked_form(request)
    email = str(form.get("email", ""))
    if _allowed(request, f"forgot:{email.strip().lower()}", 3, 60):
        try:
            request.app.state.auth_service.request_password_reset(email)
        except (OSError, smtplib.SMTPException):
            logger.exception("Password reset email failed")
    return _page(request, "message", message="如果该邮箱已注册，重置链接会发送到邮箱。")


@router.get("/reset-password", response_class=HTMLResponse)
def reset_page(request: Request, token: str = ""):
    if not token:
        return _page(request, "message", message="重置链接无效", status_code=400)
    return _page(request, "reset", reset_token=token)


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password(request: Request):
    form = await _checked_form(request)
    password = str(form.get("password", ""))
    token = str(form.get("token", ""))
    if password != str(form.get("password_confirm", "")):
        return _page(request, "reset", error="两次密码不一致", reset_token=token, status_code=422)
    try:
        valid = request.app.state.auth_service.reset_password(token, password)
    except ValueError as exc:
        return _page(request, "reset", error=str(exc), reset_token=token, status_code=422)
    if not valid:
        return _page(request, "message", message="重置链接已失效", status_code=400)
    return RedirectResponse("/auth/login", status_code=303)
