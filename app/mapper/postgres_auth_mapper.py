"""PostgreSQL accounts, one-time tokens, and revocable sessions."""

from datetime import datetime
from typing import Callable

import psycopg
from psycopg.rows import DictRow, dict_row

from app.core.config import Settings
from app.core.postgres import ensure_postgres_database
from app.mapper.base_auth_mapper import BaseAuthMapper
from app.model.auth import AuthSession, AuthUser


class PostgresAuthMapper(BaseAuthMapper):
    def __init__(
        self,
        settings: Settings | None = None,
        connection_factory: Callable[[], psycopg.Connection[DictRow]] | None = None,
    ) -> None:
        self.settings = settings
        self._connection_factory = connection_factory or self._default_connection
        if settings:
            ensure_postgres_database(settings)
        self._ensure_schema()

    def _default_connection(self) -> psycopg.Connection[DictRow]:
        if not self.settings:
            raise RuntimeError("PostgreSQL settings are required")
        return psycopg.connect(self.settings.postgres_dsn, row_factory=dict_row)

    def _connect(self) -> psycopg.Connection[DictRow]:
        return self._connection_factory()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS personal_users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE,
                    username TEXT UNIQUE,
                    display_name TEXT,
                    password_hash TEXT NOT NULL,
                    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
                    can_login_without_email_verification BOOLEAN NOT NULL DEFAULT FALSE,
                    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                    is_disabled BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL,
                    CHECK (email IS NOT NULL OR username IS NOT NULL)
                )
            """)
            connection.execute(
                "ALTER TABLE personal_users ADD COLUMN IF NOT EXISTS display_name TEXT"
            )
            connection.execute(
                "ALTER TABLE personal_users ADD COLUMN IF NOT EXISTS "
                "is_disabled BOOLEAN NOT NULL DEFAULT FALSE"
            )
            connection.execute(
                "ALTER TABLE personal_users ADD COLUMN IF NOT EXISTS "
                "can_login_without_email_verification BOOLEAN NOT NULL DEFAULT FALSE"
            )
            connection.execute("""
                CREATE TABLE IF NOT EXISTS personal_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES personal_users(id),
                    csrf_token TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    revoked_at TIMESTAMPTZ
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_personal_sessions_user ON personal_sessions(user_id)")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS personal_auth_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES personal_users(id),
                    purpose TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    consumed_at TIMESTAMPTZ
                )
            """)
            connection.commit()

    def create_user(self, user: AuthUser) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("""
                INSERT INTO personal_users
                    (id, email, username, display_name, password_hash, email_verified,
                     can_login_without_email_verification, is_admin, is_disabled, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (user.id, user.email, user.username, user.display_name, user.password_hash,
                  user.email_verified, user.can_login_without_email_verification,
                  user.is_admin, user.is_disabled, user.created_at))
            created = cursor.rowcount == 1
            connection.commit()
        return created

    def find_user(self, identifier: str) -> AuthUser | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM personal_users WHERE email = %s OR username = %s",
                (identifier, identifier),
            ).fetchone()
        return self._to_user(row) if row else None

    def get_user(self, user_id: str) -> AuthUser | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM personal_users WHERE id = %s", (user_id,)).fetchone()
        return self._to_user(row) if row else None

    def get_users(self, user_ids: list[str]) -> dict[str, AuthUser]:
        if not user_ids:
            return {}
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM personal_users WHERE id = ANY(%s)", (user_ids,)).fetchall()
        return {row["id"]: self._to_user(row) for row in rows}

    def update_display_name(self, user_id: str, display_name: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE personal_users SET display_name = %s WHERE id = %s",
                               (display_name, user_id))
            connection.commit()

    def mark_verified(self, user_id: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE personal_users SET email_verified = TRUE WHERE id = %s", (user_id,))
            connection.commit()

    def update_password(self, user_id: str, password_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE personal_users SET password_hash = %s WHERE id = %s",
                               (password_hash, user_id))
            connection.commit()

    def save_session(self, session: AuthSession) -> None:
        with self._connect() as connection:
            connection.execute("""
                INSERT INTO personal_sessions (token_hash, user_id, csrf_token, expires_at)
                VALUES (%s, %s, %s, %s)
            """, (session.token_hash, session.user_id, session.csrf_token, session.expires_at))
            connection.commit()

    def find_session(self, token_hash: str, now: datetime) -> AuthSession | None:
        with self._connect() as connection:
            row = connection.execute("""
                SELECT token_hash, user_id, csrf_token, expires_at FROM personal_sessions
                WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > %s
            """, (token_hash, now)).fetchone()
        return AuthSession(**row) if row else None

    def revoke_session(self, token_hash: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE personal_sessions SET revoked_at = NOW() WHERE token_hash = %s", (token_hash,))
            connection.commit()

    def revoke_user_sessions(self, user_id: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE personal_sessions SET revoked_at = NOW() WHERE user_id = %s", (user_id,))
            connection.commit()

    def save_token(self, token_hash: str, user_id: str, purpose: str, expires_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute("""
                INSERT INTO personal_auth_tokens (token_hash, user_id, purpose, expires_at)
                VALUES (%s, %s, %s, %s)
            """, (token_hash, user_id, purpose, expires_at))
            connection.commit()

    def consume_token(self, token_hash: str, purpose: str, now: datetime) -> str | None:
        with self._connect() as connection:
            row = connection.execute("""
                UPDATE personal_auth_tokens SET consumed_at = %s
                WHERE token_hash = %s AND purpose = %s AND consumed_at IS NULL AND expires_at > %s
                RETURNING user_id
            """, (now, token_hash, purpose, now)).fetchone()
            connection.commit()
        return row["user_id"] if row else None

    @staticmethod
    def _to_user(row: DictRow) -> AuthUser:
        return AuthUser(**dict(row))
