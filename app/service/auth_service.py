"""Email/password authentication with one-time links and revocable sessions."""

import hashlib
import hmac
import re
import secrets
import smtplib
import ssl
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from threading import RLock
from typing import Protocol

from app.core.config import Settings
from app.mapper.base_auth_mapper import BaseAuthMapper
from app.model.auth import AuthSession, AuthUser


class Mailer(Protocol):
    def send(self, recipient: str, subject: str, body: str) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.settings.smtp_from
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if self.settings.smtp_username:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)


class AttemptLimiter:
    """Small single-process limiter for a single-laptop trial deployment."""

    def __init__(self) -> None:
        self._attempts: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = RLock()

    def allow(self, key: str, limit: int, period: timedelta) -> bool:
        now = datetime.now(timezone.utc)
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= now - period:
                attempts.popleft()
            if len(attempts) >= limit:
                return False
            attempts.append(now)
            return True


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 128:
        raise ValueError("密码须为 12 至 128 个字符")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = stored.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                                n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(digest, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, mapper: BaseAuthMapper, settings: Settings, mailer: Mailer | None = None) -> None:
        self.mapper = mapper
        self.settings = settings
        self.mailer = mailer or SmtpMailer(settings)
        self.limiter = AttemptLimiter()
        self._dummy_password_hash = hash_password(secrets.token_urlsafe(24))

    @staticmethod
    def normalize_email(email: str) -> str:
        value = email.strip().lower()
        if len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("请输入有效的邮箱地址")
        return value

    def update_display_name(self, user_id: str, value: str) -> AuthUser:
        """Set a non-unique public name without changing the login identifier."""
        name = value.strip()
        if not name or len(name) > 40 or any(not char.isprintable() for char in name):
            raise ValueError("用户名请填写 1 到 40 个字符，不能包含换行或控制字符")
        self.mapper.update_display_name(user_id, name)
        user = self.mapper.get_user(user_id)
        if user is None:
            raise LookupError("账号不存在")
        return user

    def register(self, email: str, password: str, invite_code: str = "") -> AuthUser | None:
        mode = self.settings.registration_mode
        if mode == "closed":
            raise ValueError("当前暂未开放注册")
        if mode == "invite" and not hmac.compare_digest(invite_code, self.settings.registration_invite_code):
            raise ValueError("邀请码无效")
        normalized = self.normalize_email(email)
        password_hash = hash_password(password)
        user = AuthUser(
            email=normalized, password_hash=password_hash,
            display_name=f"热心用户_{normalized.split('@', 1)[0][:3]}",
            can_login_without_email_verification=not self.settings.email_verification_required,
        )
        if not self.mapper.create_user(user):
            if not self.settings.email_verification_required:
                raise ValueError("邮箱已被使用")
            existing = self.mapper.find_user(normalized)
            if existing and not existing.email_verified:
                self._send_link(existing, "verify", "验证邮箱", timedelta(hours=24))
            return None
        if self.settings.email_verification_required:
            self._send_link(user, "verify", "验证邮箱", timedelta(hours=24))
        return user

    def send_verification(self, email: str) -> None:
        try:
            user = self.mapper.find_user(self.normalize_email(email))
        except ValueError:
            return
        if user and not user.email_verified:
            self._send_link(user, "verify", "验证邮箱", timedelta(hours=24))

    def verify_email(self, token: str) -> AuthUser | None:
        user_id = self.mapper.consume_token(token_hash(token), "verify", datetime.now(timezone.utc))
        if not user_id:
            return None
        self.mapper.mark_verified(user_id)
        return self.mapper.get_user(user_id)

    def login(self, identifier: str, password: str) -> tuple[AuthUser, str, AuthSession] | None:
        normalized = identifier.strip().casefold()
        if len(normalized) > 254 or len(password) > 128:
            return None
        user = self.mapper.find_user(normalized)
        if not verify_password(password, user.password_hash if user else self._dummy_password_hash):
            return None
        if (not user or (user.email and not user.email_verified
                         and not user.can_login_without_email_verification) or user.is_disabled):
            return None
        return self.start_session(user)

    def start_session(self, user: AuthUser) -> tuple[AuthUser, str, AuthSession]:
        """Create a session after password login, registration, or email verification."""
        raw_token = secrets.token_urlsafe(32)
        session = AuthSession(
            token_hash=token_hash(raw_token),
            user_id=user.id,
            csrf_token=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        self.mapper.save_session(session)
        return user, raw_token, session

    def authenticate(self, raw_token: str | None) -> tuple[AuthUser, AuthSession] | None:
        if not raw_token:
            return None
        session = self.mapper.find_session(token_hash(raw_token), datetime.now(timezone.utc))
        user = self.mapper.get_user(session.user_id) if session else None
        return (user, session) if user and not user.is_disabled else None

    def logout(self, raw_token: str | None) -> None:
        if raw_token:
            self.mapper.revoke_session(token_hash(raw_token))

    def request_password_reset(self, email: str) -> None:
        try:
            user = self.mapper.find_user(self.normalize_email(email))
        except ValueError:
            return
        if user and user.email and user.email_verified:
            self._send_link(user, "reset", "重置密码", timedelta(minutes=30))

    def reset_password(self, token: str, new_password: str) -> bool:
        password_hash = hash_password(new_password)
        user_id = self.mapper.consume_token(token_hash(token), "reset", datetime.now(timezone.utc))
        if not user_id:
            return False
        self.mapper.update_password(user_id, password_hash)
        self.mapper.revoke_user_sessions(user_id)
        return True

    def _send_link(self, user: AuthUser, purpose: str, subject: str, lifetime: timedelta) -> None:
        if not user.email:
            return
        token = secrets.token_urlsafe(32)
        self.mapper.save_token(token_hash(token), user.id, purpose,
                               datetime.now(timezone.utc) + lifetime)
        route = "verify" if purpose == "verify" else "reset-password"
        link = f"{self.settings.public_base_url.rstrip('/')}/auth/{route}?token={token}"
        self.mailer.send(user.email, f"我的日程：{subject}", f"请打开以下链接完成{subject}：\n{link}\n\n如非本人操作，请忽略此邮件。")
