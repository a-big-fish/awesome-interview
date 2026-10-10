"""Helpers for PostgreSQL database bootstrap."""

from threading import Lock

import psycopg
from psycopg import sql

from app.core.config import Settings

_prepared_databases: set[str] = set()
_prepared_database_lock = Lock()


def ensure_postgres_database(settings: Settings) -> None:
    """Create the configured application database when it does not exist."""
    if settings.pg_dbname in _prepared_databases:
        return

    with _prepared_database_lock:
        if settings.pg_dbname in _prepared_databases:
            return
        try:
            with psycopg.connect(
                settings.postgres_admin_dsn,
                autocommit=True,
                connect_timeout=int(settings.pg_connect_timeout_seconds),
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT 1 FROM pg_database WHERE datname = %s",
                        (settings.pg_dbname,),
                    )
                    if cursor.fetchone():
                        _prepared_databases.add(settings.pg_dbname)
                        return
                    cursor.execute(
                        sql.SQL("CREATE DATABASE {}").format(
                            sql.Identifier(settings.pg_dbname)
                        )
                    )
            _prepared_databases.add(settings.pg_dbname)
        except psycopg.errors.DuplicateDatabase:
            _prepared_databases.add(settings.pg_dbname)
