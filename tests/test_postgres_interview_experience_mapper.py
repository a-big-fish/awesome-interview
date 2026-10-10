"""Check the PostgreSQL draft transaction without touching a real account."""

from datetime import timedelta

from app.mapper.postgres_interview_experience_mapper import PostgresInterviewExperienceMapper
from app.model.interview_experience import InterviewExperience, InterviewQuestion


def test_replace_draft_uses_cursor_executemany():
    experience = InterviewExperience(owner_id="owner", title="草稿")
    question = InterviewQuestion(experience_id=experience.id, category="project",
                                 asked_order=1, question_text="如何设计？")
    calls = []
    existing_rows = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def executemany(self, query, params):
            calls.append((query, params))

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, query, params):
            if "FOR UPDATE" in query or "SELECT id, payload" in query:
                return self
            return None

        def fetchone(self):
            return {"payload": experience.model_dump(mode="json")}

        def fetchall(self):
            return existing_rows

        def cursor(self):
            return Cursor()

        def commit(self):
            calls.append("commit")

    mapper = object.__new__(PostgresInterviewExperienceMapper)
    mapper._connection_factory = Connection
    updated = experience.updated_at + timedelta(seconds=1)
    saved = mapper.replace_draft(experience.id, "owner", experience.updated_at,
                                 [question], updated, {"project": 10}, 25)

    assert saved.updated_at == updated
    assert saved.category_minutes == {"project": 10}
    assert saved.total_minutes == 25
    assert len(calls[0][1]) == 1
    assert calls[0][1][0][0] == question.id
    assert calls[-1] == "commit"

    experience = saved
    existing_rows.append({"id": question.id, "payload": question.model_dump(mode="json")})
    calls.clear()
    next_saved = mapper.replace_draft(experience.id, "owner", experience.updated_at,
                                      [question], updated + timedelta(seconds=1),
                                      {"project": 10}, 25, "整体良好")
    assert next_saved.feeling == "整体良好"
    assert calls == ["commit"]
