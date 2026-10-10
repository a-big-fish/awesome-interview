from typing import Callable

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Json

from app.core.config import Settings
from app.core.postgres import ensure_postgres_database
from app.mapper.base_personal_event_mapper import BasePersonalEventMapper
from app.model.personal_event import PersonalEvent


class PostgresPersonalEventMapper(BasePersonalEventMapper):
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
            connection.execute(
                "CREATE TABLE IF NOT EXISTS personal_schedule_events ("
                "id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, payload JSONB NOT NULL, "
                "start_at TIMESTAMPTZ NOT NULL, legacy_entry_id TEXT UNIQUE)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_personal_events_owner_start "
                "ON personal_schedule_events (owner_id, start_at)"
            )
            connection.commit()

    def save(self, event: PersonalEvent) -> PersonalEvent:
        payload = event.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO personal_schedule_events "
                "(id, owner_id, payload, start_at, legacy_entry_id) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET owner_id = EXCLUDED.owner_id, "
                "payload = EXCLUDED.payload, start_at = EXCLUDED.start_at, "
                "legacy_entry_id = EXCLUDED.legacy_entry_id",
                (event.id, event.owner_id, Json(payload), event.start_at, event.legacy_entry_id),
            )
            connection.commit()
        return event.model_copy(deep=True)

    def find_by_id(self, event_id: str, owner_id: str = "local") -> PersonalEvent | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM personal_schedule_events WHERE id = %s AND owner_id = %s",
                (event_id, owner_id),
            ).fetchone()
        return PersonalEvent.model_validate(row["payload"]) if row else None

    def list_all(self, owner_id: str = "local") -> list[PersonalEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM personal_schedule_events WHERE owner_id = %s "
                "ORDER BY start_at, id",
                (owner_id,),
            ).fetchall()
        return [PersonalEvent.model_validate(row["payload"]) for row in rows]

    def delete(self, event_id: str, owner_id: str = "local") -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM personal_schedule_events WHERE id = %s AND owner_id = %s",
                (event_id, owner_id),
            )
            deleted = cursor.rowcount > 0
            connection.commit()
        return deleted
