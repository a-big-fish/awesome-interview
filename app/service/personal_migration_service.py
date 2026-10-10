from dataclasses import dataclass

from app.mapper.base_schedule_mapper import BaseScheduleMapper
from app.service.personal_schedule_service import PersonalScheduleService


@dataclass(frozen=True)
class MigrationReport:
    legacy_count: int
    existing_count: int
    created_count: int
    resume_links: int


def migrate_legacy_personal_entries(
    legacy_mapper: BaseScheduleMapper,
    personal_service: PersonalScheduleService,
    *,
    dry_run: bool = True,
) -> MigrationReport:
    """Copy 1.0 personal entries by stable ID, leaving original rows intact."""
    entries = [entry for entry in legacy_mapper.list_all() if entry.source == "personal"]
    existing_count = 0
    created_count = 0
    for entry in entries:
        if personal_service.get_event(entry.id):
            existing_count += 1
            continue
        event = personal_service.migrate_legacy_entry(entry)
        if not dry_run:
            personal_service.mapper.save(event)
        created_count += 1
    return MigrationReport(
        legacy_count=len(entries),
        existing_count=existing_count,
        created_count=created_count,
        resume_links=sum(bool(entry.resume_id) for entry in entries),
    )
