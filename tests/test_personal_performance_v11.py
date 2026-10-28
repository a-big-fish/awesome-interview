from datetime import datetime, timedelta, timezone
from dataclasses import replace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pymupdf

from app.core.dependencies import get_interview_experience_mapper, get_resume_parser_service
from app.mapper.postgres_auth_mapper import PostgresAuthMapper
from app.mapper.postgres_interview_experience_mapper import PostgresInterviewExperienceMapper
from app.model.auth import AuthSession, AuthUser
from app.model.interview_experience import InterviewExperience, InterviewQuestion
from app.model.my_resume_profile import MyResumeProfile
from app.model.resume import Resume
from app.service.auth_service import hash_password
from tests.test_public_multiuser import _login, _public_fixture


def test_auth_join_uses_one_query_and_preserves_datetime_and_revocation_predicates():
    now = datetime.now(timezone.utc)
    user = AuthUser(email="joined@example.com", created_at=now)
    session = AuthSession("hash", user.id, "csrf", now + timedelta(days=1))
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchone.return_value = {
        **session.__dict__, "user_data": {**user.__dict__, "created_at": now.isoformat()}}
    mapper = object.__new__(PostgresAuthMapper)
    mapper._connection_factory = lambda: connection
    found, found_session = mapper.authenticate_session("hash", now)
    assert found.created_at == now and found_session == session
    assert connection.execute.call_count == 1
    sql = connection.execute.call_args.args[0]
    assert "JOIN personal_users" in sql and "revoked_at IS NULL" in sql
    assert "expires_at>%s" in sql and "NOT u.is_disabled" in sql


def test_workspace_is_independent_of_file_storage_and_reads_events_once(tmp_path):
    app, auth, _, events, *_ = _public_fixture(tmp_path)
    user = AuthUser(email="shell@example.com", password_hash=hash_password("shell-test"), email_verified=True)
    auth.create_user(user)
    read_events = events.list_all
    events.list_all = MagicMock(side_effect=read_events)
    def broken_storage():
        raise RuntimeError("object storage must not be initialized by the page")
    app.dependency_overrides[get_resume_parser_service] = broken_storage
    with TestClient(app, base_url="https://testserver") as client:
        _login(client, user.email, "shell-test")
        page = client.get("/my-schedule/interviews")
        assert page.status_code == 200 and 'data-resume-cache' in page.text
        assert "同步简历" in page.text and '/resumes/' not in page.text
        assert events.list_all.call_count == 1
        # Resume state also avoids object storage.
        assert client.get("/my-schedule/resume/current").json()["resume"] is None


def test_resume_state_is_minimal_owner_scoped_and_pdf_metadata_read_once(tmp_path):
    app, auth, _, _, profiles, resumes = _public_fixture(tmp_path)
    alice = AuthUser(email="resume-state@example.com", password_hash=hash_password("resume-test"), email_verified=True)
    bob = AuthUser(email="resume-other@example.com", password_hash=hash_password("resume-test"), email_verified=True)
    auth.create_user(alice); auth.create_user(bob)
    document = pymupdf.open(); document.new_page().insert_text((72, 72), "Synthetic resume cache test")
    (tmp_path / "sample.pdf").write_bytes(document.tobytes()); document.close()
    resume = resumes.save(Resume(owner_id=alice.id, file_name="sample.pdf", pdf_path=str(tmp_path / "sample.pdf"),
                                 email="private@example.com", raw_text="private resume contents"))
    profiles.save(MyResumeProfile(id=alice.id, resume_id=resume.id))
    profiles.save(MyResumeProfile(id=bob.id, resume_id=resume.id))
    original = resumes.find_by_id
    resumes.find_by_id = MagicMock(side_effect=original)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _login(client, alice.email, "resume-test")
        state = client.get("/my-schedule/resume/current").json()["resume"]
        assert set(state) == {"id", "file_name", "version", "pdf_url"}
        assert state["id"] == resume.id
        resumes.find_by_id.reset_mock()
        assert client.get(state["pdf_url"]).content.startswith(b"%PDF-")
        assert resumes.find_by_id.call_count == 1
        first_scope = client.get("/my-schedule/interviews").text.split('data-cache-scope="')[1].split('"')[0]
        client.post("/auth/logout", data={"csrf_token": csrf})
        _login(client, bob.email, "resume-test")
        assert client.get("/my-schedule/resume/current").json()["resume"] is None
        assert client.get(state["pdf_url"]).status_code == 404
        other_scope = client.get("/my-schedule/interviews").text.split('data-cache-scope="')[1].split('"')[0]
        assert first_scope != other_scope
        auth._users[bob.id] = replace(bob, is_disabled=True)
        assert client.get("/my-schedule/profile", follow_redirects=False).status_code == 303


def test_owned_list_batches_counts_without_returning_full_text(tmp_path):
    app, auth, *_ = _public_fixture(tmp_path)
    mapper = app.dependency_overrides[get_interview_experience_mapper]()
    user = AuthUser(email="summary@example.com", password_hash=hash_password("summary-test"), email_verified=True)
    auth.create_user(user)
    item = mapper.save_experience(InterviewExperience(owner_id=user.id, title="摘要面经", is_public=False,
                                                      feeling="不应返回感受", raw_text_draft="不应返回原文"))
    mapper.save_question(InterviewQuestion(experience_id=item.id, category="project", asked_order=1,
                                           question_text="不应返回题目"), user.id)
    with TestClient(app, base_url="https://testserver") as client:
        _login(client, user.email, "summary-test")
        html = client.get("/my-schedule/experiences").text
        assert "摘要面经" in html and "1 道题" in html and "私密" in html
        assert all(text not in html for text in ("不应返回感受", "不应返回原文", "不应返回题目"))
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchall.return_value = [{"payload": item.model_dump(mode="json"), "question_count": 1}]
    postgres = object.__new__(PostgresInterviewExperienceMapper)
    postgres._connection_factory = lambda: connection
    assert postgres.list_owned_summaries(user.id)[0]["question_count"] == 1
    assert connection.execute.call_count == 1
    assert "- 'raw_text_draft' - 'feeling'" in connection.execute.call_args.args[0]


def test_postgres_event_notes_filter_owner_and_event_before_reading_payloads():
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchall.return_value = []
    mapper = object.__new__(PostgresInterviewExperienceMapper)
    mapper._connection_factory = lambda: connection
    assert mapper.list_event_experiences("owner", "event") == []
    assert connection.execute.call_count == 1
    sql, params = connection.execute.call_args.args
    assert "owner_id=%s" in sql and "linked_event_id=%s" in sql
    assert params == ("owner", "event")
