from typing import Any, Callable

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Json

from app.core.config import Settings
from app.core.postgres import ensure_postgres_database
from app.mapper.base_resume_mapper import BaseResumeMapper
from app.model.resume import Resume, ResumeImage


class PostgresResumeMapper(BaseResumeMapper):
    """PostgreSQL persistence for parsed resume metadata."""

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
                    CREATE TABLE IF NOT EXISTS interview_resumes (
                        id TEXT PRIMARY KEY,
                        owner_id TEXT NOT NULL DEFAULT 'local',
                        file_name TEXT NOT NULL,
                        pdf_path TEXT NOT NULL,
                        text_path TEXT,
                        page_count INTEGER NOT NULL DEFAULT 0,
                        candidate_name TEXT,
                        email TEXT,
                        phone TEXT,
                        raw_text TEXT NOT NULL DEFAULT '',
                        images JSONB NOT NULL DEFAULT '[]'::jsonb,
                        candidate_photo_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cursor.execute(
                    "ALTER TABLE interview_resumes ADD COLUMN IF NOT EXISTS "
                    "owner_id TEXT NOT NULL DEFAULT 'local'"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_interview_resumes_owner "
                    "ON interview_resumes (owner_id)"
                )
            connection.commit()

    def save(self, resume: Resume) -> Resume:
        values: dict[str, Any] = resume.model_dump(mode="json")
        values["images"] = Json(values["images"])
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO interview_resumes (
                        id, owner_id, file_name, pdf_path, text_path, page_count,
                        candidate_name, email, phone, raw_text, images,
                        candidate_photo_id, created_at
                    ) VALUES (
                        %(id)s, %(owner_id)s, %(file_name)s, %(pdf_path)s, %(text_path)s,
                        %(page_count)s, %(candidate_name)s, %(email)s, %(phone)s,
                        %(raw_text)s, %(images)s, %(candidate_photo_id)s,
                        %(created_at)s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        owner_id = EXCLUDED.owner_id,
                        file_name = EXCLUDED.file_name,
                        pdf_path = EXCLUDED.pdf_path,
                        text_path = EXCLUDED.text_path,
                        page_count = EXCLUDED.page_count,
                        candidate_name = EXCLUDED.candidate_name,
                        email = EXCLUDED.email,
                        phone = EXCLUDED.phone,
                        raw_text = EXCLUDED.raw_text,
                        images = EXCLUDED.images,
                        candidate_photo_id = EXCLUDED.candidate_photo_id,
                        created_at = EXCLUDED.created_at
                    RETURNING *
                    """,
                    values,
                )
                row = cursor.fetchone()
            connection.commit()
        if not row:
            raise RuntimeError("Resume metadata was not persisted")
        return self._to_model(row)

    def find_by_id(self, resume_id: str) -> Resume | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM interview_resumes WHERE id = %s",
                    (resume_id,),
                )
                row = cursor.fetchone()
        return self._to_model(row) if row else None

    @staticmethod
    def _to_model(row: DictRow) -> Resume:
        data = dict(row)
        data["images"] = [
            ResumeImage.model_validate(item) for item in (data.get("images") or [])
        ]
        data["created_at"] = _ensure_timezone(data["created_at"])
        return Resume.model_validate(data)


def _ensure_timezone(value):
    if value.tzinfo is None:
        from datetime import timezone

        return value.replace(tzinfo=timezone.utc)
    return value
