from datetime import datetime
from pathlib import Path
from typing import Callable

import psycopg
from psycopg.rows import dict_row

from app.core.config import Settings
from app.core.postgres import ensure_postgres_database
from app.mapper.base_resume_file_storage import ResumeFileStorage


class PostgresResumeFileStorage(ResumeFileStorage):
    """PostgreSQL BYTEA storage for resume PDFs, images and parsed text."""

    def __init__(
        self,
        settings: Settings | None = None,
        connection_factory: Callable[[], psycopg.Connection] | None = None,
    ) -> None:
        self.settings = settings
        self._connection_factory = connection_factory or self._default_connection
        if self.settings:
            ensure_postgres_database(self.settings)
        self._ensure_schema()

    def _default_connection(self) -> psycopg.Connection:
        if not self.settings:
            raise RuntimeError("PostgreSQL settings are required")
        return psycopg.connect(self.settings.postgres_dsn, row_factory=dict_row)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_resume_files (
                        storage_key TEXT PRIMARY KEY,
                        resume_id TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        content BYTEA NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_resume_files_resume_id "
                    "ON interview_resume_files (resume_id)"
                )
            connection.commit()

    def save_pdf(self, content: bytes, file_name: str, resume_id: str) -> str:
        suffix = self._suffix(file_name)
        storage_key = f"resumes/{resume_id}{suffix}"
        self._save(storage_key, resume_id, "application/pdf", content)
        return storage_key

    def read_pdf(self, storage_key: str) -> bytes:
        return self._read(storage_key, "application/pdf")

    def save_image(self, content: bytes, resume_id: str, image_id: str) -> str:
        storage_key = f"resume_images/{resume_id}/{image_id}.png"
        self._save(storage_key, resume_id, "image/png", content)
        return storage_key

    def read_image(self, storage_key: str) -> bytes:
        return self._read(storage_key, "image/png")

    def save_text(self, content: str, resume_id: str) -> str:
        storage_key = f"resume_info/{resume_id}.txt"
        self._save(storage_key, resume_id, "text/plain", content.encode("utf-8"))
        return storage_key

    def read_text(self, storage_key: str) -> str:
        try:
            return self._read(storage_key, "text/plain").decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Invalid resume text encoding: {storage_key}") from exc

    @staticmethod
    def _suffix(file_name: str) -> str:
        suffix = Path(file_name).suffix.lower() or ".pdf"
        return suffix

    def _save(
        self,
        storage_key: str,
        resume_id: str,
        content_type: str,
        content: bytes,
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO interview_resume_files (
                        storage_key, resume_id, content_type, content, created_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (storage_key) DO UPDATE SET
                        resume_id = EXCLUDED.resume_id,
                        content_type = EXCLUDED.content_type,
                        content = EXCLUDED.content,
                        created_at = EXCLUDED.created_at
                    """,
                    (storage_key, resume_id, content_type, content, datetime.now()),
                )
            connection.commit()

    def _read(self, storage_key: str, expected_type: str) -> bytes:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT content_type, content FROM interview_resume_files "
                    "WHERE storage_key = %s",
                    (storage_key,),
                )
                row = cursor.fetchone()
        if not row or row["content_type"] != expected_type:
            raise FileNotFoundError(storage_key)
        return bytes(row["content"])

    def _connect(self) -> psycopg.Connection:
        return self._connection_factory()
