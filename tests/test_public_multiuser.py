"""Public routing, account lifecycle, and cross-account isolation."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pymupdf
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.dependencies import (
    get_interview_experience_mapper, get_my_resume_mapper, get_personal_event_mapper,
    get_resume_parser_service, get_personal_todo_mapper,
)
from app.main import create_app
from app.mapper.memory_auth_mapper import MemoryAuthMapper
from app.mapper.memory_my_resume_mapper import MemoryMyResumeMapper
from app.mapper.memory_personal_event_mapper import MemoryPersonalEventMapper
from app.mapper.memory_personal_todo_mapper import MemoryPersonalTodoMapper
from app.mapper.memory_interview_experience_mapper import MemoryInterviewExperienceMapper
from app.mapper.memory_resume_mapper import MemoryResumeMapper
from app.model.auth import AuthUser
from app.service.auth_service import AuthService, hash_password
from app.service.resume_parser_service import ResumeParserService


class CapturingMailer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send(self, recipient: str, subject: str, body: str) -> None:
        self.messages.append((recipient, body))


def _public_fixture(tmp_path, *, email_verification_required=True, registration_mode="open"):
    settings = Settings(
        _env_file=None, app_mode="public_personal", storage_backend="postgres",
        registration_mode=registration_mode, email_verification_required=email_verification_required,
        registration_invite_code="trial-invite", smtp_host="mail.test" if email_verification_required else "",
        smtp_from="noreply@test.local" if email_verification_required else "",
        public_base_url="https://testserver",
    )
    mapper = MemoryAuthMapper()
    mailer = CapturingMailer()
    auth = AuthService(mapper, settings, mailer)
    app = create_app(settings, auth)
    events = MemoryPersonalEventMapper()
    todos = MemoryPersonalTodoMapper()
    experience_mapper = MemoryInterviewExperienceMapper()
    profiles = MemoryMyResumeMapper()
    resumes = MemoryResumeMapper()
    parser = ResumeParserService(resume_mapper=resumes, storage_dir=tmp_path)
    app.dependency_overrides[get_personal_event_mapper] = lambda: events
    app.dependency_overrides[get_personal_todo_mapper] = lambda: todos
    app.dependency_overrides[get_interview_experience_mapper] = lambda: experience_mapper
    app.dependency_overrides[get_my_resume_mapper] = lambda: profiles
    app.dependency_overrides[get_resume_parser_service] = lambda: parser
    return app, mapper, mailer, events, profiles, resumes


def _csrf(page) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match
    return match.group(1)


def _login(client: TestClient, identifier: str, password: str) -> str:
    login_page = client.get("/auth/login")
    result = client.post("/auth/login", data={
        "csrf_token": _csrf(login_page), "identifier": identifier, "password": password,
    }, follow_redirects=False)
    assert result.status_code == 303
    assert result.headers["location"] == "/my-schedule/experiences/plaza"
    return _csrf(client.get("/my-schedule/new"))


def test_mobile_snapshot_and_reminders_are_owner_scoped(tmp_path):
    app, mapper, _, _, _, _ = _public_fixture(tmp_path)
    alice = AuthUser(email="alice@example.com", password_hash=hash_password("alice-very-strong-password"), email_verified=True)
    bob = AuthUser(email="bob@example.com", password_hash=hash_password("bob-very-strong-password"), email_verified=True)
    assert mapper.create_user(alice) and mapper.create_user(bob)
    with TestClient(app, base_url="https://testserver") as alice_client, \
         TestClient(app, base_url="https://testserver") as bob_client:
        alice_csrf = _login(alice_client, alice.email, "alice-very-strong-password")
        _login(bob_client, bob.email, "bob-very-strong-password")
        created = alice_client.post("/my-schedule/events", data={
            "csrf_token": alice_csrf, "source": "manual", "title": "提醒面试",
            "event_type": "interview", "start_at": "2026-10-20T10:00",
            "end_at": "2026-10-20T11:00", "timezone": "Asia/Shanghai",
            "reminder_offsets_minutes": "60",
        }, follow_redirects=False)
        assert created.status_code == 303
        alice_snapshot = alice_client.get("/api/mobile/v1/snapshot")
        bob_snapshot = bob_client.get("/api/mobile/v1/snapshot")
        assert alice_snapshot.status_code == bob_snapshot.status_code == 200
        assert alice_snapshot.json()["user_id"] == alice.id
        assert bob_snapshot.json()["user_id"] == bob.id
        assert alice_snapshot.json()["events"][0]["reminder_offsets_minutes"] == [60]
        assert bob_snapshot.json()["events"] == []
        assert "raw_invitation" not in alice_snapshot.json()["events"][0]


def test_mobile_todos_are_owner_scoped_and_require_csrf(tmp_path):
    app, mapper, _, _, _, _ = _public_fixture(tmp_path)
    alice = AuthUser(email="alice-todo@example.com", password_hash=hash_password("alice-todo-password"), email_verified=True)
    bob = AuthUser(email="bob-todo@example.com", password_hash=hash_password("bob-todo-password"), email_verified=True)
    assert mapper.create_user(alice) and mapper.create_user(bob)
    with TestClient(app, base_url="https://testserver") as alice_client, \
         TestClient(app, base_url="https://testserver") as bob_client:
        alice_csrf = _login(alice_client, alice.email, "alice-todo-password")
        bob_csrf = _login(bob_client, bob.email, "bob-todo-password")
        token = alice_client.get("/api/mobile/v1/session").json()
        assert token == {"user_id": alice.id, "csrf_token": alice_csrf}
        assert alice_client.post("/api/mobile/v1/todos", data={
            "title": "准备面试", "due_date": "2026-10-10"}).status_code == 403
        created = alice_client.post("/api/mobile/v1/todos", data={
            "title": "准备面试", "due_date": "2026-10-10"},
            headers={"X-CSRF-Token": alice_csrf})
        assert created.status_code == 201
        todo_id = created.json()["id"]
        assert len(alice_client.get("/api/mobile/v1/snapshot").json()["todos"]) == 1
        assert bob_client.get("/api/mobile/v1/snapshot").json()["todos"] == []
        assert bob_client.post(f"/api/mobile/v1/todos/{todo_id}/toggle",
                               headers={"X-CSRF-Token": bob_csrf}).status_code == 404
        toggled = alice_client.post(f"/api/mobile/v1/todos/{todo_id}/toggle",
                                    headers={"X-CSRF-Token": alice_csrf})
        assert toggled.status_code == 200 and toggled.json()["completed_at"]
        assert bob_client.delete(f"/api/mobile/v1/todos/{todo_id}",
                                 headers={"X-CSRF-Token": bob_csrf}).status_code == 404
        assert alice_client.delete(f"/api/mobile/v1/todos/{todo_id}",
                                   headers={"X-CSRF-Token": alice_csrf}).status_code == 204
        assert alice_client.get("/api/mobile/v1/snapshot").json()["todos"] == []


def test_public_mode_closes_enterprise_routes_and_requires_login(tmp_path):
    app, _, _, _, _, _ = _public_fixture(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "Awesome Interview" in home.text
        assert "会议日程" not in home.text
        assert client.get("/my-schedule", follow_redirects=False).headers["location"].startswith("/auth/login")
        assert client.post("/my-schedule/events", data={}).status_code == 401
        assert client.get("/api/mobile/v1/snapshot").status_code == 401
        for path in ("/meetings", "/meetings/schedule", "/schedule", "/my-interviews",
                     "/interviews/old", "/api/v1/interviews", "/api/v1/resumes/parse",
                     "/docs", "/openapi.json"):
            assert client.get(path).status_code == 404, path


def test_account_registration_verification_reset_and_logout(tmp_path):
    app, _, mailer, _, _, _ = _public_fixture(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        form = client.get("/auth/register")
        created = client.post("/auth/register", data={
            "csrf_token": _csrf(form), "email": "USER@example.com",
            "password": "LongRandomPassword123!", "password_confirm": "LongRandomPassword123!",
        })
        assert created.status_code == 200
        assert mailer.messages[0][0] == "user@example.com"
        duplicate = client.post("/auth/register", data={
            "csrf_token": _csrf(client.get("/auth/register")),
            "email": "user@example.com", "password": "AnotherLongPassword123!",
            "password_confirm": "AnotherLongPassword123!",
        })
        assert duplicate.status_code == 200
        assert len(mailer.messages) == 2
        assert client.post("/auth/login", data={
            "csrf_token": _csrf(client.get("/auth/login")),
            "identifier": "user@example.com", "password": "LongRandomPassword123!",
        }).status_code == 401
        verify_token = re.search(r"token=([\w-]+)", mailer.messages[-1][1]).group(1)
        verified = client.get(f"/auth/verify?token={verify_token}", follow_redirects=False)
        assert verified.status_code == 303
        assert verified.headers["location"] == "/my-schedule/experiences/plaza"
        assert client.get("/my-schedule/experiences/plaza").status_code == 200
        assert client.get(f"/auth/verify?token={verify_token}").status_code == 400
        assert client.get("/auth/login", follow_redirects=False).status_code == 303
        csrf = _csrf(client.get("/my-schedule/new"))
        assert client.post("/auth/logout", data={"csrf_token": "wrong"}).status_code == 403
        assert client.post("/auth/logout", data={"csrf_token": csrf}, follow_redirects=False).status_code == 303
        assert client.get("/my-schedule", follow_redirects=False).status_code == 303
        forgot = client.get("/auth/forgot-password")
        assert client.post("/auth/forgot-password", data={
            "csrf_token": _csrf(forgot), "email": "user@example.com",
        }).status_code == 200
        reset_token = re.search(r"token=([\w-]+)", mailer.messages[-1][1]).group(1)
        reset = client.get(f"/auth/reset-password?token={reset_token}")
        assert client.post("/auth/reset-password", data={
            "csrf_token": _csrf(reset), "token": reset_token,
            "password": "AnotherStrongPassword123!", "password_confirm": "AnotherStrongPassword123!",
        }, follow_redirects=False).status_code == 303
        _login(client, "user@example.com", "AnotherStrongPassword123!")


def test_events_and_resume_files_are_owner_scoped(tmp_path):
    app, mapper, _, events, _, resumes = _public_fixture(tmp_path)
    alice = AuthUser(email="alice@example.com", password_hash=hash_password("alice-very-strong-password"), email_verified=True)
    bob = AuthUser(email="bob@example.com", password_hash=hash_password("bob-very-strong-password"), email_verified=True)
    assert mapper.create_user(alice) and mapper.create_user(bob)
    with TestClient(app, base_url="https://testserver") as alice_client, \
         TestClient(app, base_url="https://testserver") as bob_client:
        alice_csrf = _login(alice_client, alice.email, "alice-very-strong-password")
        bob_csrf = _login(bob_client, bob.email, "bob-very-strong-password")
        created = alice_client.post("/my-schedule/events", data={
            "csrf_token": alice_csrf, "source": "manual", "title": "Alice 的面试",
            "event_type": "interview", "start_at": "2026-10-08T10:00",
            "end_at": "2026-10-08T11:00", "timezone": "Asia/Shanghai",
        }, follow_redirects=False)
        assert created.status_code == 303
        event = events.list_all(alice.id)[0]
        assert events.list_all(bob.id) == []
        assert "Alice 的面试" not in bob_client.get("/my-schedule?date_value=2026-10-08").text
        assert bob_client.get(f"/my-schedule/events/{event.id}").status_code == 404
        assert bob_client.get(f"/my-schedule/interviews/{event.id}").status_code == 404
        assert bob_client.post(f"/my-schedule/events/{event.id}/delete",
                               data={"csrf_token": bob_csrf}).status_code == 404
        assert bob_client.post(f"/my-schedule/events/{event.id}/edit", data={
            "csrf_token": bob_csrf, "title": "Changed", "event_type": "interview",
            "start_at": "2026-10-08T10:00", "end_at": "2026-10-08T11:00",
            "timezone": "Asia/Shanghai",
        }).status_code == 404
        assert events.find_by_id(event.id, alice.id).title == "Alice 的面试"

        document = pymupdf.open()
        document.new_page().insert_text((72, 72), "Test resume")
        pdf = document.tobytes()
        document.close()
        uploaded = alice_client.post("/my-schedule/resume", data={"csrf_token": alice_csrf},
                                     files={"resume": ("resume.pdf", pdf, "application/pdf")},
                                     follow_redirects=False)
        assert uploaded.status_code == 303
        profile_resume = next(iter(resumes._resumes.values()))
        assert profile_resume.owner_id == alice.id
        assert alice_client.get(f"/resumes/{profile_resume.id}/pdf").status_code == 200
        assert bob_client.get(f"/resumes/{profile_resume.id}/pdf").status_code == 404
        assert bob_client.get(f"/resumes/{profile_resume.id}/download").status_code == 404
        assert bob_client.get(f"/resumes/{profile_resume.id}/images/nope").status_code == 404


def test_admin_username_does_not_open_enterprise_app(tmp_path):
    app, mapper, _, _, _, _ = _public_fixture(tmp_path)
    admin = AuthUser(username="admin", password_hash=hash_password("admin-random-strong-password"),
                     email_verified=True, is_admin=True)
    assert mapper.create_user(admin)
    with TestClient(app, base_url="https://testserver") as client:
        _login(client, "admin", "admin-random-strong-password")
        dashboard = client.get("/my-schedule")
        assert dashboard.status_code == 200
        assert "personal;dur=" in dashboard.headers["server-timing"]
        assert dashboard.headers["cache-control"] == "no-store"
        assert 'href="/">首页</a>' not in dashboard.text
        home = client.get("/", follow_redirects=False)
        assert home.status_code == 303
        assert home.headers["location"] == "/my-schedule/experiences/plaza"
        assert client.get("/meetings").status_code == 404


def test_display_name_settings_allow_duplicates_without_changing_login_email(tmp_path):
    app, mapper, _, _, _, _ = _public_fixture(tmp_path)
    alice = AuthUser(email="alice-name@example.com", password_hash=hash_password("alice-name-password"),
                     email_verified=True)
    bob = AuthUser(email="bob-name@example.com", password_hash=hash_password("bob-name-password"),
                   email_verified=True)
    assert mapper.create_user(alice) and mapper.create_user(bob)
    with TestClient(app, base_url="https://testserver") as alice_client, \
         TestClient(app, base_url="https://testserver") as bob_client:
        assert alice_client.get("/my-schedule/profile", follow_redirects=False).status_code == 303
        alice_csrf = _login(alice_client, alice.email, "alice-name-password")
        bob_csrf = _login(bob_client, bob.email, "bob-name-password")
        page = alice_client.get("/my-schedule/profile")
        assert page.status_code == 200
        assert 'href="/my-schedule/profile" aria-current="page"' in page.text
        assert 'value="alice-name@example.com" disabled' in page.text
        assert alice_client.post("/my-schedule/profile", data={
            "csrf_token": "wrong", "display_name": "同名用户",
        }).status_code == 403
        assert alice_client.post("/my-schedule/profile", data={
            "csrf_token": alice_csrf, "display_name": "  同名用户  ", "email": "changed@example.com",
        }, follow_redirects=False).status_code == 303
        assert bob_client.post("/my-schedule/profile", data={
            "csrf_token": bob_csrf, "display_name": "同名用户",
        }, follow_redirects=False).status_code == 303
        assert mapper.get_user(alice.id).display_name == "同名用户"
        assert mapper.get_user(bob.id).display_name == "同名用户"
        assert mapper.get_user(alice.id).email == alice.email
        assert alice_client.post("/my-schedule/profile", data={
            "csrf_token": alice_csrf, "display_name": "   ",
        }).status_code == 422
        assert mapper.get_user(alice.id).display_name == "同名用户"


def test_direct_email_registration_without_verification_or_mail(tmp_path):
    app, mapper, mailer, _, _, _ = _public_fixture(
        tmp_path, email_verification_required=False
    )
    with TestClient(app, base_url="https://testserver") as client:
        page = client.get("/auth/register")
        assert page.status_code == 200
        assert 'name="email"' in page.text
        assert "邮箱仅作为登录名" in page.text
        form = {
            "csrf_token": _csrf(page), "email": "Trial@example.com",
            "password": "long-test-password-123", "password_confirm": "long-test-password-123",
        }
        created = client.post("/auth/register", data=form, follow_redirects=False)
        assert created.status_code == 303
        assert created.headers["location"] == "/my-schedule/experiences/plaza"
        assert client.get("/my-schedule/experiences/plaza").status_code == 200
        account = mapper.find_user("trial@example.com")
        assert account.email_verified is False
        assert account.can_login_without_email_verification is True
        assert account.display_name == "热心用户_tri"
        assert account.created_at is not None
        assert mailer.messages == []
        csrf = _csrf(client.get("/my-schedule/new"))
        assert client.post("/auth/logout", data={"csrf_token": csrf}, follow_redirects=False).status_code == 303
        duplicate = client.post("/auth/register", data={**form, "csrf_token": _csrf(client.get("/auth/register"))})
        assert duplicate.status_code == 422
        _login(client, "trial@example.com", "long-test-password-123")
        assert client.get("/auth/forgot-password").status_code == 404
        assert client.get("/auth/resend-verification").status_code == 404


def test_expired_login_form_renders_new_form_instead_of_raw_error(tmp_path):
    app, mapper, _, _, _, _ = _public_fixture(tmp_path, email_verification_required=False)
    user = AuthUser(email="stale@example.com", password_hash=hash_password("stale-password-123"),
                    can_login_without_email_verification=True)
    mapper.create_user(user)
    with TestClient(app, base_url="https://testserver") as client:
        stale = client.post("/auth/login", data={
            "csrf_token": "expired", "identifier": user.email, "password": "stale-password-123",
        })
        assert stale.status_code == 403
        assert "登录表单已过期，请重新提交" in stale.text
        assert 'name="csrf_token"' in stale.text
        login = client.post("/auth/login", data={
            "csrf_token": _csrf(stale), "identifier": user.email, "password": "stale-password-123",
        }, follow_redirects=False)
        assert login.status_code == 303
        assert login.headers["location"] == "/my-schedule/experiences/plaza"
