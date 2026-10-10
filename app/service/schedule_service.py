from datetime import datetime
from typing import Any

from app.controller.schema.schedule_dto import MeetingEntryCreateDTO
from app.core.exceptions import EntryNotFoundError, MeetingParseError, ScheduleConflictWarning
from interviewschedule.utils.time_utils import ensure_timezone, now
from app.mapper.base_schedule_mapper import BaseScheduleMapper
from app.mapper.memory_schedule_mapper import MemoryScheduleMapper
from app.model.enums import EntryStatus, MeetingSource
from app.model.meeting_entry import MeetingEntry
from app.service.meeting_parser_service import MeetingParserService
from app.service.enterprise_calendar_service import EnterpriseCalendarService


class ScheduleService:
    def __init__(
        self,
        schedule_mapper: BaseScheduleMapper | None = None,
        meeting_parser: MeetingParserService | None = None,
        calendar_service: EnterpriseCalendarService | None = None,
    ) -> None:
        self.schedule_mapper = schedule_mapper or MemoryScheduleMapper()
        self.meeting_parser = meeting_parser or MeetingParserService()
        self.calendar_service = calendar_service

    def create_from_invitation(
        self, dto: MeetingEntryCreateDTO, confirm_non_working: bool = False,
        reviewed_fields: dict[str, Any] | None = None,
    ) -> MeetingEntry:
        if dto.source_id:
            existing = self.schedule_mapper.find_by_source_id(dto.source_id)
            if existing:
                return existing
        try:
            entry = self.meeting_parser.parse(dto)
        except MeetingParseError:
            raise
        if reviewed_fields:
            entry = MeetingEntry.model_validate({**entry.model_dump(), **reviewed_fields})
        duplicate = self.schedule_mapper.find_duplicate(entry)
        if duplicate:
            return duplicate
        if not confirm_non_working:
            warnings = self.non_working_warnings(entry)
            if warnings:
                raise ScheduleConflictWarning(warnings)
        return self.schedule_mapper.save(entry)

    def non_working_warnings(self, entry: MeetingEntry) -> list[str]:
        """Return soft warnings for an enterprise meeting without changing data."""
        if self.calendar_service is None or entry.source == MeetingSource.PERSONAL.value:
            return []
        return self.calendar_service.overlap_warnings(entry.start_time, entry.end_time)

    def list_non_personal(self) -> list[MeetingEntry]:
        """List candidate interviews, excluding the own-interview workspace."""
        return [entry for entry in self.list_all() if entry.source != MeetingSource.PERSONAL.value]

    def list_overview(self, now: datetime) -> dict[str, list[MeetingEntry]]:
        """Group candidate interviews for the schedule overview.

        Returns ``{"finished": [...], "today": [...]}`` for non-personal entries:
        ``finished`` holds every interview that has already ended, and ``today``
        holds interviews scheduled today that have not ended yet.
        """
        current = ensure_timezone(now)
        today_date = current.date()
        finished: list[MeetingEntry] = []
        today: list[MeetingEntry] = []
        for entry in self.list_non_personal():
            if entry.kind != "interview":
                continue
            if entry.status_at(current) == EntryStatus.FINISHED:
                finished.append(entry)
            elif entry.start_time.date() == today_date:
                today.append(entry)
        finished.sort(key=lambda entry: entry.start_time, reverse=True)
        today.sort(key=lambda entry: entry.start_time)
        return {"finished": finished, "today": today}

    def get_daily_schedule(self, date: str) -> list[MeetingEntry]:
        return [
            entry for entry in self.schedule_mapper.find_by_date(date)
            if entry.source != MeetingSource.PERSONAL.value
        ]

    def list_all(self) -> list[MeetingEntry]:
        return self.schedule_mapper.list_all()

    def get_entry(self, entry_id: str) -> MeetingEntry:
        entry = self.schedule_mapper.find_by_id(entry_id)
        if not entry:
            raise EntryNotFoundError("面试记录不存在")
        return entry

    def attach_resume(self, entry_id: str, resume_id: str) -> MeetingEntry:
        """Associate an uploaded resume with an existing schedule entry."""
        entry = self.schedule_mapper.find_by_id(entry_id)
        if not entry:
            raise EntryNotFoundError("面试记录不存在")
        entry.resume_id = resume_id
        return self.schedule_mapper.save(entry)

    def delete_entry(self, entry_id: str) -> None:
        if not self.schedule_mapper.delete(entry_id):
            raise EntryNotFoundError("面试记录不存在")

    def list_dates(self) -> list[str]:
        return sorted({entry.date for entry in self.list_all()})

    def current_status_time(self):
        return now()
