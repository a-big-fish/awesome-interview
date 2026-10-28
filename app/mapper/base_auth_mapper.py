"""Persistence boundary for public accounts and sessions."""

from abc import ABC, abstractmethod
from datetime import date, datetime

from app.model.auth import AuthSession, AuthUser


class BaseAuthMapper(ABC):
    def authenticate_session(self, token_hash: str, now: datetime) -> tuple[AuthUser, AuthSession] | None:
        session = self.find_session(token_hash, now)
        user = self.get_user(session.user_id) if session else None
        return (user, session) if user and not user.is_disabled else None

    @abstractmethod
    def create_user(self, user: AuthUser) -> bool: ...

    @abstractmethod
    def find_user(self, identifier: str) -> AuthUser | None: ...

    @abstractmethod
    def get_user(self, user_id: str) -> AuthUser | None: ...

    @abstractmethod
    def get_users(self, user_ids: list[str]) -> dict[str, AuthUser]: ...

    @abstractmethod
    def registration_counts_by_day(self) -> dict[date, int]: ...

    @abstractmethod
    def update_display_name(self, user_id: str, display_name: str) -> None: ...

    @abstractmethod
    def mark_verified(self, user_id: str) -> None: ...

    @abstractmethod
    def update_password(self, user_id: str, password_hash: str) -> None: ...

    @abstractmethod
    def save_session(self, session: AuthSession) -> None: ...

    @abstractmethod
    def find_session(self, token_hash: str, now: datetime) -> AuthSession | None: ...

    @abstractmethod
    def revoke_session(self, token_hash: str) -> None: ...

    @abstractmethod
    def revoke_user_sessions(self, user_id: str) -> None: ...

    @abstractmethod
    def save_token(self, token_hash: str, user_id: str, purpose: str, expires_at: datetime) -> None: ...

    @abstractmethod
    def consume_token(self, token_hash: str, purpose: str, now: datetime) -> str | None: ...
