from typing import Callable

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Json

from app.core.config import Settings
from app.core.postgres import ensure_postgres_database
from app.mapper.base_personal_todo_mapper import BasePersonalTodoMapper
from app.model.personal_todo import PersonalTodo


class PostgresPersonalTodoMapper(BasePersonalTodoMapper):
    def __init__(self, settings: Settings | None = None,
                 connection_factory: Callable[[], psycopg.Connection[DictRow]] | None = None) -> None:
        self.settings = settings
        self._connection_factory = connection_factory or self._default_connection
        if settings:
            ensure_postgres_database(settings)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS personal_todos ("
                "id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, due_date DATE NOT NULL, "
                "payload JSONB NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_personal_todos_owner_due "
                "ON personal_todos (owner_id, due_date)"
            )
            connection.commit()

    def _default_connection(self) -> psycopg.Connection[DictRow]:
        if not self.settings:
            raise RuntimeError("PostgreSQL settings are required")
        return psycopg.connect(self.settings.postgres_dsn, row_factory=dict_row)

    def _connect(self) -> psycopg.Connection[DictRow]:
        return self._connection_factory()

    def save(self, todo: PersonalTodo) -> PersonalTodo:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO personal_todos (id, owner_id, due_date, payload) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET "
                "owner_id = EXCLUDED.owner_id, due_date = EXCLUDED.due_date, payload = EXCLUDED.payload",
                (todo.id, todo.owner_id, todo.due_date, Json(todo.model_dump(mode="json"))),
            )
            connection.commit()
        return todo.model_copy(deep=True)

    def find_by_id(self, todo_id: str, owner_id: str) -> PersonalTodo | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM personal_todos WHERE id = %s AND owner_id = %s",
                (todo_id, owner_id),
            ).fetchone()
        return PersonalTodo.model_validate(row["payload"]) if row else None

    def list_all(self, owner_id: str) -> list[PersonalTodo]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM personal_todos WHERE owner_id = %s ORDER BY due_date, id",
                (owner_id,),
            ).fetchall()
        return [PersonalTodo.model_validate(row["payload"]) for row in rows]

    def delete(self, todo_id: str, owner_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM personal_todos WHERE id = %s AND owner_id = %s",
                (todo_id, owner_id),
            )
            connection.commit()
        return cursor.rowcount > 0
