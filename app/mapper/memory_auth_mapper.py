"""In-memory account store for isolated tests and local experiments."""

from dataclasses import replace
from datetime import datetime
from threading import RLock

from app.mapper.base_auth_mapper import BaseAuthMapper
from app.model.auth import AuthSession, AuthUser


class MemoryAuthMapper(BaseAuthMapper):
    def __init__(self) -> None:
        self._users: dict[str, AuthUser] = {}
        self._sessions: dict[str, AuthSession] = {}
        self._tokens: dict[str, tuple[str, str, datetime]] = {}
        self._lock = RLock()

    def create_user(self, user: AuthUser) -> bool:
        with self._lock:
            if any(
                item.id == user.id
                or (user.email and item.email == user.email)
                or (user.username and item.username == user.username)
                for item in self._users.values()
            ):
                return False
            self._users[user.id] = user
            return True

    def find_user(self, identifier: str) -> AuthUser | None:
        identifier = identifier.strip().casefold()
        with self._lock:
            return next((user for user in self._users.values()
                         if user.email == identifier or user.username == identifier), None)

    def get_user(self, user_id: str) -> AuthUser | None:
        with self._lock:
            return self._users.get(user_id)

    def get_users(self, user_ids: list[str]) -> dict[str, AuthUser]:
        with self._lock:
            return {user_id: self._users[user_id] for user_id in user_ids if user_id in self._users}

    def update_display_name(self, user_id: str, display_name: str) -> None:
        with self._lock:
            self._users[user_id] = replace(self._users[user_id], display_name=display_name)

    def mark_verified(self, user_id: str) -> None:
        with self._lock:
            self._users[user_id] = replace(self._users[user_id], email_verified=True)

    def update_password(self, user_id: str, password_hash: str) -> None:
        with self._lock:
            self._users[user_id] = replace(self._users[user_id], password_hash=password_hash)

    def save_session(self, session: AuthSession) -> None:
        with self._lock:
            self._sessions[session.token_hash] = session

    def find_session(self, token_hash: str, now: datetime) -> AuthSession | None:
        with self._lock:
            session = self._sessions.get(token_hash)
            return session if session and session.expires_at > now else None

    def revoke_session(self, token_hash: str) -> None:
        with self._lock:
            self._sessions.pop(token_hash, None)

    def revoke_user_sessions(self, user_id: str) -> None:
        with self._lock:
            self._sessions = {key: session for key, session in self._sessions.items()
                              if session.user_id != user_id}

    def save_token(self, token_hash: str, user_id: str, purpose: str, expires_at: datetime) -> None:
        with self._lock:
            self._tokens[token_hash] = (user_id, purpose, expires_at)

    def consume_token(self, token_hash: str, purpose: str, now: datetime) -> str | None:
        with self._lock:
            record = self._tokens.get(token_hash)
            if record and record[1] == purpose and record[2] > now:
                del self._tokens[token_hash]
                return record[0]
            return None
