"""Administrator statistics stay aggregate-only and isolated from regular users."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.core.dependencies import get_interview_experience_mapper
from app.mapper.memory_auth_mapper import MemoryAuthMapper
from app.mapper.memory_interview_experience_mapper import MemoryInterviewExperienceMapper
from app.model.auth import AuthUser
from app.model.interview_experience import InterviewExperience
from app.service.admin_dashboard_service import build_admin_dashboard
from app.service.auth_service import hash_password
from tests.test_public_multiuser import _login, _public_fixture


def test_dashboard_counts_users_and_both_visibility_states_by_creation_day():
    users = MemoryAuthMapper()
    notes = MemoryInterviewExperienceMapper()
    for index, day in enumerate((3, 3, 4)):
        users.create_user(AuthUser(email=f"user-{index}@example.com",
                                   created_at=datetime(2026, 10, day, tzinfo=timezone.utc)))
    notes.save_experience(InterviewExperience(owner_id="a", title="公开",
                                              is_public=True,
                                              created_at=datetime(2026, 10, 3, tzinfo=ZoneInfo("Asia/Shanghai"))))
    notes.save_experience(InterviewExperience(owner_id="b", title="私密内容",
                                              is_public=False,
                                              created_at=datetime(2026, 10, 4, tzinfo=ZoneInfo("Asia/Shanghai"))))
    stats = build_admin_dashboard(users, notes, date(2026, 10, 4))
    assert (stats["total_users"], stats["total_notes"], stats["total_public"],
            stats["total_private"]) == (3, 2, 1, 1)
    assert stats["series"][-2]["users"] == 2
    assert stats["series"][-1]["private"] == 1
    assert len(stats["series"]) == 30


def test_dashboard_requires_admin_and_never_renders_private_note_text(tmp_path):
    app, mapper, _, _, _, _ = _public_fixture(tmp_path)
    notes = app.dependency_overrides[get_interview_experience_mapper]()
    admin = AuthUser(username="admin", password_hash=hash_password("admin-password"),
                     email_verified=True, is_admin=True)
    ordinary = AuthUser(email="ordinary@example.com", password_hash=hash_password("ordinary-password"),
                        email_verified=True)
    mapper.create_user(admin)
    mapper.create_user(ordinary)
    notes.save_experience(InterviewExperience(owner_id=ordinary.id, title="绝不展示的私密标题",
                                              is_public=False))
    with TestClient(app, base_url="https://testserver") as guest, \
         TestClient(app, base_url="https://testserver") as regular, \
         TestClient(app, base_url="https://testserver") as privileged:
        assert guest.get("/my-schedule/admin", follow_redirects=False).status_code == 303
        _login(regular, ordinary.email, "ordinary-password")
        assert regular.get("/my-schedule/admin").status_code == 403
        assert "数据看板" not in regular.get("/my-schedule/new").text
        _login(privileged, "admin", "admin-password")
        response = privileged.get("/my-schedule/admin")
        assert response.status_code == 200
        assert "注册用户" in response.text and "私密面经" in response.text
        assert "绝不展示的私密标题" not in response.text
        assert "数据看板" in privileged.get("/my-schedule/new").text
        assert response.headers["cache-control"] == "no-store"
