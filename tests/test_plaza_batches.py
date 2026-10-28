import re
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.dependencies import get_interview_experience_mapper
from app.mapper.memory_interview_experience_mapper import MemoryInterviewExperienceMapper
from app.mapper.postgres_interview_experience_mapper import PostgresInterviewExperienceMapper
from app.model.auth import AuthUser
from app.model.interview_experience import InterviewExperience, InterviewQuestion
from app.service.auth_service import hash_password
from tests.test_public_multiuser import _login, _public_fixture


def seed(mapper, owner):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(45):
        item = InterviewExperience(id=f"note-{index:02}", owner_id=owner, title=f"笔记 {index}",
                                   company="测试公司", feeling="概述" * 100,
                                   raw_text_draft="不应返回的私有原文",
                                   interviewed_at=start + timedelta(days=index) if index < 43 else None)
        mapper.save_experience(item)
        mapper.save_question(InterviewQuestion(experience_id=item.id, category="project", asked_order=1,
                                               question_text="问题"), owner)


def test_streamed_batches_have_no_duplicates_and_keep_filters_authors_and_privacy(tmp_path):
    app, auth, *_ = _public_fixture(tmp_path)
    mapper = app.dependency_overrides[get_interview_experience_mapper]()
    user = AuthUser(email="batch@example.com", password_hash=hash_password("batch-test"),
                    display_name="批量作者", email_verified=True)
    auth.create_user(user)
    seed(mapper, user.id)
    hidden = [{"company": "测试公司", "feeling": "概述", "is_public": False},
              {"company": " ", "feeling": "概述"}, {"company": "测试公司"}]
    for index, fields in enumerate(hidden):
        mapper.save_experience(InterviewExperience(owner_id=user.id, title=f"隐藏 {index}", **fields))
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/my-schedule/experiences/plaza?batch=true", follow_redirects=False).status_code == 303
        _login(client, user.email, "batch-test")
        initial = client.get("/my-schedule/experiences/plaza")
        assert len(re.findall('data-plaza-id=', initial.text)) == 20
        assert 'data-next-page="2"' in initial.text and "上一页" not in initial.text
        seen = []
        for page, expected in [(1, 20), (2, 20), (3, 5), (4, 0)]:
            response = client.get(f"/my-schedule/experiences/plaza?batch=true&page={page}")
            assert response.status_code == 200
            data = response.json()
            ids = re.findall('data-plaza-id="([^"]+)"', data["html"])
            assert len(ids) == expected and data["total"] == 45
            assert data["next_page"] == (page + 1 if page < 3 else None)
            assert "隐藏" not in data["html"] and "私有原文" not in data["html"]
            if ids:
                assert "作者：批量作者" in data["html"] and "1 道问题" in data["html"]
            seen.extend(ids)
        assert len(seen) == len(set(seen)) == 45
        assert seen[:2] == ["note-42", "note-41"]
        assert seen[-2:] == ["note-44", "note-43"]
        filtered = client.get("/my-schedule/experiences/plaza?batch=true&company=不存在").json()
        assert filtered["total"] == 0 and filtered["next_page"] is None
        oldest = client.get("/my-schedule/experiences/plaza?batch=true&order=oldest").json()
        assert re.findall('data-plaza-id="([^"]+)"', oldest["html"])[0] == "note-00"
        # Server-rendered fragment continues to escape authored text.
        item = mapper.find_experience("note-42", user.id)
        item.title = "<script>alert('unsafe')</script>"
        mapper.save_experience(item)
        assert "<script>" not in client.get("/my-schedule/experiences/plaza?batch=true").json()["html"]


def test_memory_batch_limits_payload_and_treats_filter_as_literal():
    mapper = MemoryInterviewExperienceMapper()
    seed(mapper, "owner")
    items, total = mapper.list_public_batch("公司", "newest", 20, 20)
    assert total == 45 and len(items) == 20
    assert all(not row["experience"].raw_text_draft and len(row["experience"].feeling) <= 111 for row in items)
    assert mapper.find_experience("note-00", "owner").raw_text_draft
    assert mapper.list_public_batch("%_", "newest", 0, 20) == ([], 0)


def test_postgres_batch_reads_current_batch_and_counts_in_one_execute():
    calls = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params):
            calls.append((sql, params))
            return self
        def fetchall(self): return [{"total": 39, "payload": None, "question_count": 0}]
    mapper = object.__new__(PostgresInterviewExperienceMapper)
    mapper._connection_factory = Connection
    assert mapper.list_public_batch("%_", "oldest", 40, 20) == ([], 39)
    assert len(calls) == 1
    sql, params = calls[0]
    assert "LIMIT %s OFFSET %s" in sql and "ASC NULLS LAST" in sql
    assert params == ("%\\%\\_%", 20, 40)
