"""PostgreSQL storage for independently owned interview experiences."""

from typing import Callable
from datetime import date, datetime

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Json

from app.core.performance import timed_postgres_connect
from app.core.config import Settings
from app.core.postgres import ensure_postgres_database
from app.mapper.base_interview_experience_mapper import BaseInterviewExperienceMapper
from app.model.interview_experience import InterviewExperience, InterviewQuestion


class PostgresInterviewExperienceMapper(BaseInterviewExperienceMapper):
    def __init__(self, settings: Settings | None = None,
                 connection_factory: Callable[[], psycopg.Connection[DictRow]] | None = None) -> None:
        self.settings = settings
        self._connection_factory = connection_factory or self._default_connection
        if settings:
            ensure_postgres_database(settings)
        self._ensure_schema()

    def _default_connection(self) -> psycopg.Connection[DictRow]:
        if not self.settings:
            raise RuntimeError("PostgreSQL settings are required")
        return timed_postgres_connect(self.settings.postgres_dsn, row_factory=dict_row)

    def _connect(self) -> psycopg.Connection[DictRow]:
        return self._connection_factory()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS personal_interview_experiences ("
                "id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, linked_event_id TEXT, "
                "updated_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_personal_experiences_owner "
                "ON personal_interview_experiences (owner_id, updated_at DESC)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS personal_interview_questions ("
                "id TEXT PRIMARY KEY, experience_id TEXT NOT NULL "
                "REFERENCES personal_interview_experiences(id) ON DELETE CASCADE, "
                "asked_order INTEGER NOT NULL, payload JSONB NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_personal_questions_experience "
                "ON personal_interview_questions (experience_id, asked_order)"
            )
            connection.commit()

    def save_experience(self, experience: InterviewExperience) -> InterviewExperience:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO personal_interview_experiences (id, owner_id, linked_event_id, "
                "updated_at, payload) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET linked_event_id=EXCLUDED.linked_event_id, "
                "updated_at=EXCLUDED.updated_at, payload=EXCLUDED.payload "
                "WHERE personal_interview_experiences.owner_id=EXCLUDED.owner_id",
                (experience.id, experience.owner_id, experience.linked_event_id,
                 experience.updated_at, Json(experience.model_dump(mode="json"))),
            )
            connection.commit()
        return experience.model_copy(deep=True)

    def find_experience(self, experience_id: str, owner_id: str) -> InterviewExperience | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM personal_interview_experiences WHERE id=%s AND owner_id=%s",
                (experience_id, owner_id),
            ).fetchone()
        return InterviewExperience.model_validate(row["payload"]) if row else None

    def list_experiences(self, owner_id: str) -> list[InterviewExperience]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM personal_interview_experiences WHERE owner_id=%s "
                "ORDER BY updated_at DESC, id DESC", (owner_id,),
            ).fetchall()
        return [InterviewExperience.model_validate(row["payload"]) for row in rows]

    def experience_counts_by_day(self) -> dict[date, tuple[int, int]]:
        """Aggregate visibility for every saved experience without reading note text."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT (COALESCE(NULLIF(payload->>'created_at', '')::timestamptz, updated_at) "
                "AT TIME ZONE 'Asia/Shanghai')::date AS day, "
                "COUNT(*) FILTER (WHERE COALESCE((payload->>'is_public')::boolean, TRUE)) "
                "AS public_count, "
                "COUNT(*) FILTER (WHERE NOT COALESCE((payload->>'is_public')::boolean, TRUE)) "
                "AS private_count FROM personal_interview_experiences GROUP BY day"
            ).fetchall()
        return {row["day"]: (row["public_count"], row["private_count"]) for row in rows}

    def list_owned_summaries(self, owner_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT e.payload - 'raw_text_draft' - 'feeling' AS payload, "
                "(SELECT COUNT(*) FROM personal_interview_questions q WHERE q.experience_id=e.id) "
                "AS question_count FROM personal_interview_experiences e WHERE e.owner_id=%s "
                "ORDER BY e.updated_at DESC, e.id DESC", (owner_id,),
            ).fetchall()
        return [{"experience": InterviewExperience.model_validate(row["payload"]),
                 "question_count": row["question_count"]} for row in rows]

    def list_event_experiences(self, owner_id: str, event_id: str) -> list[InterviewExperience]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM personal_interview_experiences WHERE owner_id=%s "
                "AND linked_event_id=%s ORDER BY updated_at DESC, id DESC", (owner_id, event_id),
            ).fetchall()
        return [InterviewExperience.model_validate(row["payload"]) for row in rows]

    def list_public_experiences(self) -> list[InterviewExperience]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload - 'raw_text_draft' AS payload FROM personal_interview_experiences "
                "WHERE COALESCE((payload->>'is_public')::boolean, TRUE) "
                "AND NULLIF(BTRIM(COALESCE(payload->>'company', '')), '') IS NOT NULL "
                "AND (NULLIF(BTRIM(COALESCE(payload->>'feeling', '')), '') IS NOT NULL "
                "OR EXISTS (SELECT 1 FROM personal_interview_questions q "
                "WHERE q.experience_id=personal_interview_experiences.id))"
            ).fetchall()
        return [InterviewExperience.model_validate(row["payload"]) for row in rows]

    def find_public_experience(self, experience_id: str) -> InterviewExperience | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload - 'raw_text_draft' AS payload FROM personal_interview_experiences "
                "WHERE id=%s AND COALESCE((payload->>'is_public')::boolean, TRUE)",
                (experience_id,),
            ).fetchone()
        return InterviewExperience.model_validate(row["payload"]) if row else None

    def list_public_batch(self, company: str, order: str, offset: int,
                          limit: int) -> tuple[list[dict], int]:
        direction = "ASC" if order == "oldest" else "DESC"
        pattern = "%" + company.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        # Select the batch first; count questions only for those IDs. The seed row
        # preserves the total even when the requested batch is empty.
        query = (
            "WITH eligible AS (SELECT id, payload FROM personal_interview_experiences e "
            "WHERE COALESCE((payload->>'is_public')::boolean, TRUE) "
            "AND NULLIF(BTRIM(COALESCE(payload->>'company', '')), '') IS NOT NULL "
            "AND COALESCE(payload->>'company', '') ILIKE %s "
            "AND (NULLIF(BTRIM(COALESCE(payload->>'feeling', '')), '') IS NOT NULL "
            "OR EXISTS (SELECT 1 FROM personal_interview_questions q WHERE q.experience_id=e.id))), "
            "batch AS (SELECT id, payload, NULLIF(payload->>'interviewed_at', '')::timestamptz AS interviewed "
            f"FROM eligible ORDER BY interviewed {direction} NULLS LAST, id {direction} LIMIT %s OFFSET %s) "
            "SELECT (SELECT COUNT(*) FROM eligible) AS total, "
            "b.payload - 'raw_text_draft' - 'feeling' || "
            "jsonb_build_object('feeling', LEFT(b.payload->>'feeling', 111)) AS payload, "
            "(SELECT COUNT(*) FROM personal_interview_questions q WHERE q.experience_id=b.id) AS question_count "
            "FROM (SELECT 1) seed LEFT JOIN batch b ON TRUE "
            f"ORDER BY b.interviewed {direction} NULLS LAST, b.id {direction}"
        )
        with self._connect() as connection:
            rows = connection.execute(query, (pattern, limit, offset)).fetchall()
        return ([{"experience": InterviewExperience.model_validate(row["payload"]),
                  "question_count": row["question_count"]} for row in rows if row["payload"]],
                rows[0]["total"] if rows else 0)

    def list_public_questions(self, experience_id: str) -> list[InterviewQuestion]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT q.payload FROM personal_interview_questions q "
                "JOIN personal_interview_experiences e ON e.id=q.experience_id "
                "WHERE e.id=%s AND COALESCE((e.payload->>'is_public')::boolean, TRUE) "
                "ORDER BY q.asked_order, q.id", (experience_id,),
            ).fetchall()
        return [InterviewQuestion.model_validate(row["payload"]) for row in rows]

    def count_public_questions(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT q.experience_id, COUNT(*) AS question_count "
                "FROM personal_interview_questions q "
                "JOIN personal_interview_experiences e ON e.id=q.experience_id "
                "WHERE COALESCE((e.payload->>'is_public')::boolean, TRUE) "
                "GROUP BY q.experience_id"
            ).fetchall()
        return {row["experience_id"]: row["question_count"] for row in rows}

    def count_questions_by_experience(self, owner_id: str) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT q.experience_id, COUNT(*) AS question_count "
                "FROM personal_interview_questions q "
                "JOIN personal_interview_experiences e ON e.id=q.experience_id "
                "WHERE e.owner_id=%s GROUP BY q.experience_id", (owner_id,),
            ).fetchall()
        return {row["experience_id"]: row["question_count"] for row in rows}

    def delete_experience(self, experience_id: str, owner_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM personal_interview_experiences WHERE id=%s AND owner_id=%s",
                (experience_id, owner_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def save_question(self, question: InterviewQuestion, owner_id: str) -> InterviewQuestion:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO personal_interview_questions (id, experience_id, asked_order, payload) "
                "SELECT %s, id, %s, %s FROM personal_interview_experiences "
                "WHERE id=%s AND owner_id=%s "
                "ON CONFLICT (id) DO UPDATE SET asked_order=EXCLUDED.asked_order, "
                "payload=EXCLUDED.payload WHERE personal_interview_questions.experience_id="
                "EXCLUDED.experience_id",
                (question.id, question.asked_order, Json(question.model_dump(mode="json")),
                 question.experience_id, owner_id),
            )
            if cursor.rowcount != 1:
                raise LookupError("面经不存在")
            connection.commit()
        return question.model_copy(deep=True)

    def find_question(self, question_id: str, owner_id: str) -> InterviewQuestion | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT q.payload FROM personal_interview_questions q "
                "JOIN personal_interview_experiences e ON e.id=q.experience_id "
                "WHERE q.id=%s AND e.owner_id=%s", (question_id, owner_id),
            ).fetchone()
        return InterviewQuestion.model_validate(row["payload"]) if row else None

    def list_questions(self, experience_id: str, owner_id: str) -> list[InterviewQuestion]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT q.payload FROM personal_interview_questions q "
                "JOIN personal_interview_experiences e ON e.id=q.experience_id "
                "WHERE e.id=%s AND e.owner_id=%s ORDER BY q.asked_order, q.id",
                (experience_id, owner_id),
            ).fetchall()
        return [InterviewQuestion.model_validate(row["payload"]) for row in rows]

    def delete_questions(self, question_ids: list[str], owner_id: str) -> None:
        if not question_ids:
            return
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM personal_interview_questions q USING personal_interview_experiences e "
                "WHERE q.experience_id=e.id AND e.owner_id=%s AND q.id=ANY(%s)",
                (owner_id, question_ids),
            )
            connection.commit()

    def replace_draft(self, experience_id: str, owner_id: str, expected_updated_at: datetime,
                      questions: list[InterviewQuestion], updated_at: datetime,
                      category_minutes: dict[str, int] | None = None,
                      total_minutes: int | None = None,
                      feeling: str | None = None,
                      raw_text_draft: str | None = None) -> InterviewExperience:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM personal_interview_experiences WHERE id=%s AND owner_id=%s FOR UPDATE",
                (experience_id, owner_id),
            ).fetchone()
            if not row:
                raise LookupError("面经不存在")
            experience = InterviewExperience.model_validate(row["payload"])
            if experience.updated_at != expected_updated_at:
                raise RuntimeError("面经已在其他页面修改，请刷新后核对草稿")
            existing_rows = connection.execute(
                "SELECT id, payload FROM personal_interview_questions WHERE experience_id=%s",
                (experience_id,),
            ).fetchall()
            existing = {row["id"]: row["payload"] for row in existing_rows}
            current = {item.id: item.model_dump(mode="json") for item in questions}
            removed = list(existing.keys() - current.keys())
            if removed:
                connection.execute(
                    "DELETE FROM personal_interview_questions WHERE experience_id=%s AND id=ANY(%s)",
                    (experience_id, removed),
                )
            changed = [item for item in questions if existing.get(item.id) != current[item.id]]
            if changed:
                with connection.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO personal_interview_questions (id, experience_id, asked_order, payload) "
                        "VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET "
                        "asked_order=EXCLUDED.asked_order, payload=EXCLUDED.payload",
                        [(item.id, experience_id, item.asked_order, Json(current[item.id]))
                         for item in changed],
                    )
            if category_minutes is not None:
                experience.category_minutes = category_minutes.copy()
                experience.total_minutes = total_minutes
            if feeling is not None:
                experience.feeling = feeling.strip() or None
            if raw_text_draft is not None:
                experience.raw_text_draft = raw_text_draft
            experience.updated_at = updated_at
            connection.execute(
                "UPDATE personal_interview_experiences SET updated_at=%s, payload=%s WHERE id=%s",
                (updated_at, Json(experience.model_dump(mode="json")), experience_id),
            )
            connection.commit()
        return experience
