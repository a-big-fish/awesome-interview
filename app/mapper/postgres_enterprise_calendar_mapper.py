from typing import Callable

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Json

from app.core.config import Settings
from app.core.postgres import ensure_postgres_database
from app.mapper.base_enterprise_calendar_mapper import BaseEnterpriseCalendarMapper
from app.model.enterprise_calendar import EnterpriseCalendarSettings


class PostgresEnterpriseCalendarMapper(BaseEnterpriseCalendarMapper):
    def __init__(
        self,
        settings: Settings | None = None,
        connection_factory: Callable[[], psycopg.Connection[DictRow]] | None = None,
    ) -> None:
        self.settings = settings
        self._connection_factory = connection_factory or self._default_connection
        if settings:
            ensure_postgres_database(settings)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS enterprise_calendar_settings "
                "(id TEXT PRIMARY KEY, payload JSONB NOT NULL)"
            )
            connection.commit()

    def _default_connection(self) -> psycopg.Connection[DictRow]:
        if not self.settings:
            raise RuntimeError("PostgreSQL settings are required")
        return psycopg.connect(self.settings.postgres_dsn, row_factory=dict_row)

    def _connect(self) -> psycopg.Connection[DictRow]:
        return self._connection_factory()

    def get(self) -> EnterpriseCalendarSettings | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM enterprise_calendar_settings WHERE id = %s", ("default",)
            ).fetchone()
        return EnterpriseCalendarSettings.model_validate(row["payload"]) if row else None

    def save(self, settings: EnterpriseCalendarSettings) -> EnterpriseCalendarSettings:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO enterprise_calendar_settings (id, payload) VALUES (%s, %s) "
                "ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload",
                ("default", Json(settings.model_dump(mode="json"))),
            )
            connection.commit()
        return settings.model_copy(deep=True)
