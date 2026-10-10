"""Account and session records used by the public personal application."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class AuthUser:
    id: str = field(default_factory=lambda: str(uuid4()))
    email: str | None = None
    username: str | None = None
    display_name: str | None = None
    password_hash: str = ""
    email_verified: bool = False
    can_login_without_email_verification: bool = False
    is_admin: bool = False
    is_disabled: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class AuthSession:
    token_hash: str
    user_id: str
    csrf_token: str
    expires_at: datetime
