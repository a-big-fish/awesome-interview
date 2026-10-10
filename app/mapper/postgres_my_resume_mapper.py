from datetime import datetime
from typing import Any, Callable

import psycopg
from psycopg.rows import DictRow, dict_row

from app.core.config import Settings
from app.core.postgres import ensure_postgres_database
from app.mapper.base_my_resume_mapper import BaseMyResumeMapper
from app.model.my_resume_profile import MyResumeProfile


class PostgresMyResumeMapper(BaseMyResumeMapper):
    """PostgreSQL storage for the current user's resume profile."""

    def __init__(
        self,
        settings: Settings | None = None,
        connection_factory: Callable[[], psycopg.Connection[DictRow]] | None = None,
    ) -> None:
        self.settings = settings
        self._connection_factory = connection_factory or self._default_connection
        if self.settings:
            ensure_postgres_database(self.settings)
        self._ensure_schema()

    def _default_connection(self) -> psycopg.Connection[DictRow]:
        if not self.settings:
            raise RuntimeError("PostgreSQL settings are required")
        return psycopg.connect(self.settings.postgres_dsn, row_factory=dict_row)

    def _connect(self) -> psycopg.Connection[DictRow]:
        return self._connection_factory()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS my_resume_profiles (
                        id TEXT PRIMARY KEY,
                        resume_id TEXT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            connection.commit()

    def save(self, profile: MyResumeProfile) -> MyResumeProfile:
        values: dict[str, Any] = profile.model_dump(mode="json")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO my_resume_profiles (id, resume_id, updated_at)
                    VALUES (%(id)s, %(resume_id)s, %(updated_at)s)
                    ON CONFLICT (id) DO UPDATE SET
                        resume_id = EXCLUDED.resume_id,
                        updated_at = EXCLUDED.updated_at
                    RETURNING *
                    """,
                    values,
                )
                row = cursor.fetchone()
            connection.commit()
        if not row:
            raise RuntimeError("My resume profile was not persisted")
        return self._to_model(row)

    def get(self, profile_id: str = "default") -> MyResumeProfile | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM my_resume_profiles WHERE id = %s",
                    (profile_id,),
                )
                row = cursor.fetchone()
        return self._to_model(row) if row else None

    @staticmethod
    def _to_model(row: DictRow) -> MyResumeProfile:
        data = dict(row)
        data["updated_at"] = _ensure_timezone(data["updated_at"])
        return MyResumeProfile.model_validate(data)


def _ensure_timezone(value: datetime) -> datetime:
    from datetime import timezone

    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
