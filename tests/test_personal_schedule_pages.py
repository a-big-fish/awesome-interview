from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.core.dependencies import get_my_resume_mapper, get_personal_schedule_service, get_resume_parser_service
from app.main import app
from app.mapper.memory_my_resume_mapper import MemoryMyResumeMapper
from app.mapper.memory_personal_event_mapper import MemoryPersonalEventMapper
from app.mapper.memory_resume_mapper import MemoryResumeMapper
from app.model.my_resume_profile import MyResumeProfile
from app.model.resume import Resume
from app.service.personal_schedule_service import PersonalScheduleService
from app.service.resume_parser_service import ResumeParserService


def test_personal_manual_create_edit_and_delete_pages():
    profile = MemoryMyResumeMapper()
    service = PersonalScheduleService(MemoryPersonalEventMapper(), profile)
    app.dependency_overrides[get_personal_schedule_service] = lambda: service
    app.dependency_overrides[get_my_resume_mapper] = lambda: profile
    try:
        with TestClient(app) as client:
            assert client.get("/my-schedule/new").status_code == 200
            created = client.post("/my-schedule/events", data={
                "source": "manual", "title": "算法笔试", "event_type": "exam",
                "start_at": "2026-10-02T09:00", "end_at": "2026-10-02T10:00",
                "timezone": "Asia/Shanghai", "location_text": "教学楼 A",
            }, follow_redirects=False)
            assert created.status_code == 303
            event = service.list_events()[0]
            assert event.type == "exam"
            non_interview = client.get(f"/my-schedule/interviews/{event.id}", follow_redirects=False)
            assert non_interview.status_code == 303
            assert non_interview.headers["location"] == f"/my-schedule/events/{event.id}"
            page = client.get("/my-schedule?date_value=2026-10-02")
            assert "算法笔试" in page.text
            assert "候选人姓名" not in page.text
            detail = client.get(f"/my-schedule/events/{event.id}")
            assert detail.status_code == 200
            edited = client.post(f"/my-schedule/events/{event.id}/edit", data={
                "title": "算法笔试第二轮", "event_type": "exam",
                "start_at": "2026-10-02T09:00", "end_at": "2026-10-02T10:00",
                "timezone": "Asia/Shanghai",
            }, follow_redirects=False)
            assert edited.status_code == 303
            assert service.get_event(event.id).title == "算法笔试第二轮"
            deleted = client.post(f"/my-schedule/events/{event.id}/delete", follow_redirects=False)
            assert deleted.status_code == 303
            assert service.list_events() == []
    finally:
        app.dependency_overrides.pop(get_personal_schedule_service, None)
        app.dependency_overrides.pop(get_my_resume_mapper, None)


def test_new_personal_event_defaults_to_current_shanghai_time():
    before = datetime.now(ZoneInfo("Asia/Shanghai")).replace(second=0, microsecond=0)
    with TestClient(app) as client:
        page = client.get("/my-schedule/new")
    after = datetime.now(ZoneInfo("Asia/Shanghai")).replace(second=0, microsecond=0)
    assert page.status_code == 200
    start = re.search(r'name="start_at" value="([^"]+)"', page.text)
    end = re.search(r'name="end_at" value="([^"]+)"', page.text)
    assert start and end
    start_at = datetime.fromisoformat(start.group(1))
    end_at = datetime.fromisoformat(end.group(1))
    assert before.replace(tzinfo=None) <= start_at <= after.replace(tzinfo=None)
    assert end_at - start_at == timedelta(hours=1)


def test_non_interview_event_form_hides_invitation_parser_on_validation_error():
    with TestClient(app) as client:
        page = client.post("/my-schedule/events", data={
            "title": "课程", "event_type": "course", "start_at": "invalid",
            "end_at": "invalid", "timezone": "Asia/Shanghai",
        })
    assert page.status_code == 422
    assert 'data-invitation-form hidden' in page.text
    assert 'name="event_type" form="personal-event-form"' in page.text


def test_personal_calendar_has_live_time_line_and_hides_it_on_other_dates():
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    with TestClient(app) as client:
        current = client.get("/my-schedule", params={"date_value": today.isoformat()})
        previous = client.get("/my-schedule", params={
            "date_value": (today - timedelta(days=1)).isoformat(),
        })
    assert 'data-now-grid' in current.text
    assert 'data-time-zone="Asia/Shanghai"' in current.text
    assert 'data-now-line' in current.text
    assert 'data-now-line hidden' in previous.text


def test_personal_calendar_week_and_month_views_keep_period_navigation():
    profile = MemoryMyResumeMapper()
    service = PersonalScheduleService(MemoryPersonalEventMapper(), profile)
    service.create_manual(
        title="周内面试", event_type="interview",
        start_at=datetime(2026, 10, 9, 9, tzinfo=ZoneInfo("Asia/Shanghai")),
        end_at=datetime(2026, 10, 9, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    app.dependency_overrides[get_personal_schedule_service] = lambda: service
    try:
        with TestClient(app) as client:
            week = client.get("/my-schedule?view=week&date_value=2026-10-10")
            month = client.get("/my-schedule?view=month&date_value=2026-10-10")
        assert week.status_code == month.status_code == 200
        assert 'personal-period-week' in week.text
        assert '2026-10-05 — 10-11 · 1 项安排' in week.text
        assert 'view=week&amp;date_value=2026-10-03' in week.text
        assert 'class="personal-today-link" href="/my-schedule?view=week&amp;date_value=' in week.text
        assert '周内面试' in week.text
        assert 'personal-period-month' in month.text
        assert '2026 年 10 月 · 1 项安排' in month.text
        assert 'view=month&amp;date_value=2026-11-01' in month.text
        assert 'class="personal-today-link" href="/my-schedule?view=month&amp;date_value=' in month.text
        assert '查看 2026-11-01 的日程' in month.text
    finally:
        app.dependency_overrides.pop(get_personal_schedule_service, None)


def test_personal_invitation_preview_and_interview_workspace():
    profile = MemoryMyResumeMapper()
    service = PersonalScheduleService(MemoryPersonalEventMapper(), profile)
    app.dependency_overrides[get_personal_schedule_service] = lambda: service
    app.dependency_overrides[get_my_resume_mapper] = lambda: profile
    raw = "会议主题：后端面试\n面试时间：2026/10/02 13:00-14:00\n"
    try:
        with TestClient(app) as client:
            preview = client.post("/my-schedule/parse", data={"raw_text": raw})
            assert preview.status_code == 200
            assert "后端面试" in preview.text
            assert service.list_events() == []
            saved = client.post("/my-schedule/events", data={
                "source": "invitation", "raw_text": raw, "title": "后端面试",
                "event_type": "interview", "start_at": "2026-10-02T13:00",
                "end_at": "2026-10-02T14:00", "timezone": "Asia/Shanghai",
            }, follow_redirects=False)
            assert saved.status_code == 303
            workspace = client.get("/my-schedule/interviews?date_value=2026-10-02")
            assert workspace.status_code == 200
            assert "后端面试" in workspace.text
            assert "我的简历" in workspace.text
            assert 'class="my-interviews-main"' in workspace.text
            assert 'class="my-interview-layout"' in workspace.text
            assert 'class="date-tabs-row"' in workspace.text
            assert 'data-date-scope' not in workspace.text
            assert 'class="plan-group-title today"' in workspace.text
            assert 'class="plan-group-title finished"' in workspace.text
            event = service.list_events()[0]
            assert f'href="/my-schedule/interviews/{event.id}"' in workspace.text
            questions = client.get(f"/my-schedule/interviews/{event.id}")
            assert questions.status_code == 200
            assert 'class="card my-resume-panel"' in questions.text
            assert 'class="card interview-questions-panel"' in questions.text
            assert "还没有问题记录" in questions.text
            assert "返回面试计划" in questions.text
            assert 'class="card schedule-group"' not in questions.text
            assert 'class="card my-plan-panel"' not in questions.text
    finally:
        app.dependency_overrides.pop(get_personal_schedule_service, None)
        app.dependency_overrides.pop(get_my_resume_mapper, None)


def test_personal_interview_resume_uses_original_full_page_view(tmp_path):
    profile = MemoryMyResumeMapper()
    resumes = MemoryResumeMapper()
    saved = resumes.save(Resume(file_name="sample.pdf", pdf_path="sample.pdf", page_count=1))
    profile.save(MyResumeProfile(resume_id=saved.id))
    service = PersonalScheduleService(MemoryPersonalEventMapper(), profile)
    app.dependency_overrides[get_personal_schedule_service] = lambda: service
    app.dependency_overrides[get_my_resume_mapper] = lambda: profile
    app.dependency_overrides[get_resume_parser_service] = lambda: ResumeParserService(
        resume_mapper=resumes, storage_dir=tmp_path,
    )
    try:
        with TestClient(app) as client:
            page = client.get("/my-schedule/interviews")
            assert page.status_code == 200
            assert 'class="card my-resume-panel"' in page.text
            assert 'class="own-resume-a4"' in page.text
            assert 'class="resume-replace-form"' in page.text
            assert 'data-file-input hidden' in page.text
            assert 'src="/resumes/' + saved.id + '/pdf"' in page.text
    finally:
        app.dependency_overrides.pop(get_personal_schedule_service, None)
        app.dependency_overrides.pop(get_my_resume_mapper, None)
        app.dependency_overrides.pop(get_resume_parser_service, None)


def test_personal_overlap_can_be_confirmed_from_form():
    profile = MemoryMyResumeMapper()
    service = PersonalScheduleService(MemoryPersonalEventMapper(), profile)
    service.create_manual(
        title="课程", event_type="course",
        start_at=datetime(2026, 10, 2, 9, tzinfo=ZoneInfo("Asia/Shanghai")),
        end_at=datetime(2026, 10, 2, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    app.dependency_overrides[get_personal_schedule_service] = lambda: service
    form = {
        "source": "manual", "title": "笔试", "event_type": "exam",
        "start_at": "2026-10-02T09:30", "end_at": "2026-10-02T10:30",
        "timezone": "Asia/Shanghai",
    }
    try:
        with TestClient(app) as client:
            warning = client.post("/my-schedule/events", data=form)
            assert warning.status_code == 409
            assert "课程" in warning.text
            assert len(service.list_events()) == 1
            accepted = client.post("/my-schedule/events", data={**form, "confirm_overlap": "true"}, follow_redirects=False)
            assert accepted.status_code == 303
            assert len(service.list_events()) == 2
    finally:
        app.dependency_overrides.pop(get_personal_schedule_service, None)
