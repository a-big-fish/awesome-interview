from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.exceptions import PersonalEventConflictWarning
from app.mapper.memory_my_resume_mapper import MemoryMyResumeMapper
from app.mapper.memory_personal_event_mapper import MemoryPersonalEventMapper
from app.model.my_resume_profile import MyResumeProfile
from app.model.personal_event import PersonalEvent
from app.service.personal_schedule_service import PersonalScheduleService


def _service() -> PersonalScheduleService:
    return PersonalScheduleService(MemoryPersonalEventMapper(), MemoryMyResumeMapper())


def test_manual_event_and_soft_overlap_warning():
    service = _service()
    start = datetime(2026, 10, 2, 9, 0)
    end = datetime(2026, 10, 2, 10, 0)
    first = service.create_manual(title="算法笔试", event_type="exam", start_at=start, end_at=end)
    assert first.type == "exam"
    assert first.start_at.isoformat() == "2026-10-02T09:00:00+08:00"
    with pytest.raises(PersonalEventConflictWarning, match="重叠"):
        service.create_manual(
            title="课程", event_type="course",
            start_at=datetime(2026, 10, 2, 9, 30),
            end_at=datetime(2026, 10, 2, 10, 30),
        )
    assert len(service.list_events()) == 1
    service.create_manual(
        title="课程", event_type="course",
        start_at=datetime(2026, 10, 2, 9, 30),
        end_at=datetime(2026, 10, 2, 10, 30),
        confirm_overlap=True,
    )
    assert len(service.list_events()) == 2


def test_invitation_uses_shared_parser_without_candidate_field():
    profile = MemoryMyResumeMapper()
    profile.save(MyResumeProfile(resume_id="resume-1"))
    service = PersonalScheduleService(MemoryPersonalEventMapper(), profile)
    event = service.create_from_invitation(
        "面试时间：2026/10/02 13:00-14:00\n会议主题：后端面试\n"
    )
    assert event.type == "interview"
    assert event.resume_id == "resume-1"
    assert "candidate_name" not in PersonalEvent.model_fields
    assert event.source == "invitation"
    assert service.create_from_invitation(event.raw_invitation).id == event.id


def test_update_and_delete_are_owner_scoped():
    service = _service()
    event = service.create_manual(
        title="宣讲会", event_type="recruiting",
        start_at=datetime(2026, 10, 2, 9, tzinfo=ZoneInfo("Asia/Shanghai")),
        end_at=datetime(2026, 10, 2, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    updated = service.update_event(event.id, title="企业宣讲会")
    assert updated.title == "企业宣讲会"
    assert service.delete_event(event.id)
    assert service.get_event(event.id) is None
