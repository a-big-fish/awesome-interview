from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.exceptions import PersonalEventConflictWarning
from app.mapper.base_my_resume_mapper import BaseMyResumeMapper
from app.mapper.base_personal_event_mapper import BasePersonalEventMapper
from app.model.meeting_entry import MeetingEntry
from app.model.personal_event import PersonalEvent, PersonalEventType
from app.shared.invitation_parser import InvitationParser


def _localize(value: datetime, timezone_name: str) -> datetime:
    return value.replace(tzinfo=ZoneInfo(timezone_name)) if value.tzinfo is None else value


class PersonalScheduleService:
    """Own the job seeker's events without candidate-oriented enterprise fields."""

    def __init__(
        self,
        mapper: BasePersonalEventMapper,
        profile_mapper: BaseMyResumeMapper,
        parser: InvitationParser | None = None,
        owner_id: str = "local",
    ) -> None:
        self.mapper = mapper
        self.profile_mapper = profile_mapper
        self.parser = parser or InvitationParser()
        self.owner_id = owner_id

    @property
    def profile_id(self) -> str:
        return "default" if self.owner_id == "local" else self.owner_id

    def list_events(self) -> list[PersonalEvent]:
        return self.mapper.list_all(self.owner_id)

    def get_event(self, event_id: str) -> PersonalEvent | None:
        return self.mapper.find_by_id(event_id, self.owner_id)

    def conflicting_events(self, proposed: PersonalEvent) -> list[PersonalEvent]:
        return [
            event for event in self.list_events()
            if event.id != proposed.id
            and proposed.start_at < event.end_at
            and proposed.end_at > event.start_at
        ]

    def save_event(self, event: PersonalEvent, confirm_overlap: bool = False) -> PersonalEvent:
        if event.owner_id != self.owner_id:
            raise ValueError("不能保存其他用户的日程")
        conflicts = self.conflicting_events(event)
        if conflicts and not confirm_overlap:
            raise PersonalEventConflictWarning([item.title for item in conflicts])
        event.updated_at = datetime.now(ZoneInfo("Asia/Shanghai"))
        return self.mapper.save(event)

    def create_manual(
        self,
        *,
        title: str,
        event_type: PersonalEventType,
        start_at: datetime,
        end_at: datetime,
        timezone: str = "Asia/Shanghai",
        location_text: str | None = None,
        location_url: str | None = None,
        note: str | None = None,
        position: str | None = None,
        reminder_offsets_minutes: list[int] | None = None,
        confirm_overlap: bool = False,
    ) -> PersonalEvent:
        profile = self.profile_mapper.get(self.profile_id) if event_type == "interview" else None
        event = PersonalEvent(
            owner_id=self.owner_id,
            type=event_type,
            title=title.strip(),
            start_at=_localize(start_at, timezone),
            end_at=_localize(end_at, timezone),
            timezone=timezone,
            location_text=location_text or None,
            location_url=location_url or None,
            note=note or None,
            position=position or None if event_type == "interview" else None,
            resume_id=profile.resume_id if profile else None,
            reminder_offsets_minutes=reminder_offsets_minutes or [],
        )
        return self.save_event(event, confirm_overlap)

    def from_invitation(
        self,
        raw_text: str,
        *,
        title: str | None = None,
        event_type: PersonalEventType | None = None,
        position: str | None = None,
        timezone: str = "Asia/Shanghai",
        note: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        platform: str | None = None,
        meeting_url: str | None = None,
        location_text: str | None = None,
        reminder_offsets_minutes: list[int] | None = None,
    ) -> PersonalEvent:
        """Preview a shared parser result as a personal event without persisting it."""
        facts = self.parser.parse_facts(raw_text)
        resolved_type: PersonalEventType = event_type or (
            "interview" if facts.kind_hint == "interview" else "meeting"
        )
        profile = self.profile_mapper.get(self.profile_id)
        return PersonalEvent(
            owner_id=self.owner_id,
            type=resolved_type,
            title=(title or facts.subject or ("未命名面试" if resolved_type == "interview" else "未命名会议")).strip(),
            start_at=_localize(start_at, timezone) if start_at else facts.start_time,
            end_at=_localize(end_at, timezone) if end_at else facts.end_time,
            timezone=timezone,
            source="invitation",
            raw_invitation=raw_text,
            position=(position or facts.position_hint) if resolved_type == "interview" else None,
            platform=platform or facts.platform,
            room_number=facts.room_number,
            meeting_url=meeting_url or facts.meeting_url,
            location_text=location_text or None,
            note=note or None,
            resume_id=profile.resume_id if profile and resolved_type == "interview" else None,
            reminder_offsets_minutes=reminder_offsets_minutes or [],
        )

    def create_from_invitation(self, raw_text: str, confirm_overlap: bool = False, **kwargs) -> PersonalEvent:
        event = self.from_invitation(raw_text, **kwargs)
        for existing in self.list_events():
            if (existing.start_at == event.start_at and existing.end_at == event.end_at
                    and existing.title == event.title and existing.meeting_url == event.meeting_url):
                return existing
        return self.save_event(event, confirm_overlap)

    def update_event(self, event_id: str, confirm_overlap: bool = False, **changes) -> PersonalEvent:
        current = self.get_event(event_id)
        if not current:
            raise LookupError("日程不存在")
        timezone = changes.get("timezone", current.timezone)
        if changes.get("type", current.type) != "interview":
            changes["resume_id"] = None
            changes["position"] = None
        elif current.type != "interview":
            profile = self.profile_mapper.get(self.profile_id)
            changes["resume_id"] = profile.resume_id if profile else None
        for key in ("start_at", "end_at"):
            if key in changes and isinstance(changes[key], datetime):
                changes[key] = _localize(changes[key], timezone)
        updated = current.model_copy(update=changes)
        updated = PersonalEvent.model_validate(updated.model_dump())
        return self.save_event(updated, confirm_overlap)

    def delete_event(self, event_id: str) -> bool:
        return self.mapper.delete(event_id, self.owner_id)

    def migrate_legacy_entry(self, entry: MeetingEntry) -> PersonalEvent:
        """Map a 1.0 personal entry while preserving its identifier and resume link."""
        if entry.source != "personal":
            raise ValueError("只能迁移个人面试记录")
        event_type: PersonalEventType = "interview" if entry.kind == "interview" else "meeting"
        return PersonalEvent(
            id=entry.id,
            owner_id=self.owner_id,
            type=event_type,
            title=entry.subject,
            start_at=entry.start_time,
            end_at=entry.end_time,
            source="migrated",
            raw_invitation=entry.raw_text,
            position=entry.position if event_type == "interview" else None,
            platform=entry.platform,
            room_number=entry.room_number,
            meeting_url=entry.meeting_url,
            note=entry.note,
            resume_id=entry.resume_id if event_type == "interview" else None,
            legacy_entry_id=entry.id,
            created_at=entry.created_at,
        )
