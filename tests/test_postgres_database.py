from psycopg.conninfo import conninfo_to_dict

from app.core import postgres
from app.core.config import Settings


def test_postgres_dsn_quotes_database_name():
    settings = Settings(
        _env_file=None,
        pg_dbname="interview-system",
        pg_host="db.example",
        pg_port=5432,
        pg_user="admin",
        pg_password="secret phrase",
    )

    info = conninfo_to_dict(settings.postgres_dsn)
    admin_info = conninfo_to_dict(settings.postgres_admin_dsn)

    assert info["dbname"] == "interview-system"
    assert info["password"] == "secret phrase"
    assert admin_info["dbname"] == "postgres"


def test_ensure_postgres_database_creates_missing_database_once(monkeypatch):
    settings = Settings(
        _env_file=None,
        pg_dbname="interview-system",
        pg_host="db.example",
        pg_user="admin",
        pg_password="secret",
    )
    created = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params=None):
            if "CREATE DATABASE" in str(query):
                created.append(params)

        def fetchone(self):
            return None

    class FakeConnection:
        autocommit = False

        def __init__(self):
            self.cursor_result = FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return self.cursor_result

    connections = []

    def fake_connect(dsn, autocommit=False, connect_timeout=5):
        connections.append(dsn)
        connection = FakeConnection()
        connection.autocommit = autocommit
        return connection

    monkeypatch.setattr(postgres.psycopg, "connect", fake_connect)
    monkeypatch.setattr(postgres, "_prepared_databases", set())

    postgres.ensure_postgres_database(settings)
    postgres.ensure_postgres_database(settings)

    assert len(connections) == 1
    assert created
