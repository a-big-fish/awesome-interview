from datetime import datetime
from zoneinfo import ZoneInfo

from app.mapper.memory_my_resume_mapper import MemoryMyResumeMapper
from app.mapper.memory_personal_event_mapper import MemoryPersonalEventMapper
from app.mapper.memory_schedule_mapper import MemoryScheduleMapper
from app.model.meeting_entry import MeetingEntry
from app.service.personal_migration_service import migrate_legacy_personal_entries
from app.service.personal_schedule_service import PersonalScheduleService


def test_migration_dry_run_then_idempotent_copy_preserves_resume_link():
    old = MemoryScheduleMapper()
    source = old.save(MeetingEntry(
        candidate_name="本人",
        subject="后端面试",
        source="personal",
        start_time=datetime(2026, 10, 2, 13, tzinfo=ZoneInfo("Asia/Shanghai")),
        end_time=datetime(2026, 10, 2, 14, tzinfo=ZoneInfo("Asia/Shanghai")),
        resume_id="resume-1",
    ))
    personal = PersonalScheduleService(MemoryPersonalEventMapper(), MemoryMyResumeMapper())
    dry = migrate_legacy_personal_entries(old, personal)
    assert (dry.legacy_count, dry.created_count) == (1, 1)
    assert personal.list_events() == []
    applied = migrate_legacy_personal_entries(old, personal, dry_run=False)
    assert applied.created_count == 1
    migrated = personal.get_event(source.id)
    assert migrated is not None
    assert migrated.resume_id == "resume-1"
    assert migrated.legacy_entry_id == source.id
    assert old.find_by_id(source.id) is not None
    again = migrate_legacy_personal_entries(old, personal, dry_run=False)
    assert again.created_count == 0
    assert again.existing_count == 1
