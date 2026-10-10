from datetime import datetime
from typing import Any, Callable

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Json

from app.core.config import Settings
from app.core.postgres import ensure_postgres_database
from app.mapper.base_schedule_mapper import BaseScheduleMapper
from app.model.meeting_entry import MeetingEntry


class PostgresScheduleMapper(BaseScheduleMapper):
    """PostgreSQL persistence for interview schedule metadata."""

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
        return psycopg.connect(
            self.settings.postgres_dsn,
            row_factory=dict_row,
        )

    def _connect(self) -> psycopg.Connection[DictRow]:
        return self._connection_factory()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS interview_schedule_entries (
                        id TEXT PRIMARY KEY,
                        candidate_name TEXT NOT NULL,
                        position TEXT,
                        subject TEXT NOT NULL,
                        kind TEXT NOT NULL DEFAULT 'interview',
                        start_time TIMESTAMPTZ NOT NULL,
                        end_time TIMESTAMPTZ NOT NULL,
                        platform TEXT NOT NULL,
                        room_number TEXT,
                        meeting_url TEXT,
                        interviewer_names JSONB NOT NULL DEFAULT '[]'::jsonb,
                        source TEXT NOT NULL,
                        source_id TEXT,
                        candidate_external_id TEXT,
                        note TEXT,
                        raw_text TEXT,
                        resume_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cursor.execute(
                    "ALTER TABLE interview_schedule_entries "
                    "ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'interview'"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_schedule_start_time "
                    "ON interview_schedule_entries (start_time)"
                )
                cursor.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_source_id "
                    "ON interview_schedule_entries (source_id) "
                    "WHERE source_id IS NOT NULL"
                )
            connection.commit()

    def save(self, entry: MeetingEntry) -> MeetingEntry:
        values: dict[str, Any] = entry.model_dump(mode="json")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO interview_schedule_entries (
                        id, candidate_name, position, subject, kind, start_time, end_time,
                        platform, room_number, meeting_url, interviewer_names, source,
                        source_id, candidate_external_id, note, raw_text, resume_id,
                        created_at
                    ) VALUES (
                        %(id)s, %(candidate_name)s, %(position)s, %(subject)s,
                        %(kind)s, %(start_time)s, %(end_time)s, %(platform)s, %(room_number)s,
                        %(meeting_url)s, %(interviewer_names)s, %(source)s,
                        %(source_id)s, %(candidate_external_id)s, %(note)s,
                        %(raw_text)s, %(resume_id)s, %(created_at)s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        candidate_name = EXCLUDED.candidate_name,
                        position = EXCLUDED.position,
                        subject = EXCLUDED.subject,
                        kind = EXCLUDED.kind,
                        start_time = EXCLUDED.start_time,
                        end_time = EXCLUDED.end_time,
                        platform = EXCLUDED.platform,
                        room_number = EXCLUDED.room_number,
                        meeting_url = EXCLUDED.meeting_url,
                        interviewer_names = EXCLUDED.interviewer_names,
                        source = EXCLUDED.source,
                        source_id = EXCLUDED.source_id,
                        candidate_external_id = EXCLUDED.candidate_external_id,
                        note = EXCLUDED.note,
                        raw_text = EXCLUDED.raw_text,
                        resume_id = EXCLUDED.resume_id,
                        created_at = EXCLUDED.created_at
                    RETURNING *
                    """,
                    {
                        **values,
                        "interviewer_names": Json(values["interviewer_names"]),
                    },
                )
                row = cursor.fetchone()
            connection.commit()
        if not row:
            raise RuntimeError("Schedule entry was not persisted")
        return self._to_model(row)

    def find_by_id(self, entry_id: str) -> MeetingEntry | None:
        return self._find_one("id = %s", (entry_id,))

    def find_by_date(self, date: str) -> list[MeetingEntry]:
        return self._find_many(
            "WHERE start_time::date = %s::date",
            (date,),
        )

    def list_all(self) -> list[MeetingEntry]:
        return self._find_many()

    def find_duplicate(self, entry: MeetingEntry) -> MeetingEntry | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM interview_schedule_entries
                    WHERE start_time = %s
                      AND kind = %s
                      AND end_time = %s
                      AND subject = %s
                      AND platform = %s
                      AND room_number IS NOT DISTINCT FROM %s
                      AND meeting_url IS NOT DISTINCT FROM %s
                    ORDER BY created_at, id
                    LIMIT 1
                    """,
                    (
                        entry.start_time,
                        entry.kind,
                        entry.end_time,
                        entry.subject,
                        entry.platform,
                        entry.room_number,
                        str(entry.meeting_url) if entry.meeting_url else None,
                    ),
                )
                row = cursor.fetchone()
        return self._to_model(row) if row else None

    def find_by_source_id(self, source_id: str) -> MeetingEntry | None:
        return self._find_one("source_id = %s", (source_id,))

    def delete(self, entry_id: str) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM interview_schedule_entries WHERE id = %s",
                    (entry_id,),
                )
                deleted = cursor.rowcount > 0
            connection.commit()
        return deleted

    def _find_one(self, condition: str, params: tuple[Any, ...]) -> MeetingEntry | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM interview_schedule_entries WHERE {condition}",
                    params,
                )
                row = cursor.fetchone()
        return self._to_model(row) if row else None

    def _find_many(
        self, condition: str | None = None, params: tuple[Any, ...] = ()
    ) -> list[MeetingEntry]:
        query = "SELECT * FROM interview_schedule_entries"
        if condition:
            query += f" {condition}"
        query += " ORDER BY start_time"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [self._to_model(row) for row in rows]

    @staticmethod
    def _to_model(row: DictRow) -> MeetingEntry:
        data = dict(row)
        data["interviewer_names"] = data.get("interviewer_names") or []
        data["start_time"] = _ensure_timezone(data["start_time"])
        data["end_time"] = _ensure_timezone(data["end_time"])
        data["created_at"] = _ensure_timezone(data["created_at"])
        return MeetingEntry.model_validate(data)


def _ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        from datetime import timezone

        return value.replace(tzinfo=timezone.utc)
    return value
