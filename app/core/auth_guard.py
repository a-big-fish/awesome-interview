"""Request authentication and CSRF checks for the public personal router."""

import hmac

from fastapi import Request

from app.model.auth import AuthUser


SESSION_COOKIE = "schedule_session"


class AuthRequired(Exception):
    """Raised when a public personal resource has no valid session."""


class InvalidCsrf(Exception):
    """Raised when a state-changing request lacks its session CSRF value."""


async def require_current_user(request: Request) -> AuthUser:
    result = request.app.state.auth_service.authenticate(request.cookies.get(SESSION_COOKIE))
    if not result:
        raise AuthRequired
    user, session = result
    request.state.user = user
    request.state.csrf_token = session.csrf_token
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        form = await request.form()
        submitted = str(form.get("csrf_token", "")) or request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(submitted, session.csrf_token):
            raise InvalidCsrf
    return user
