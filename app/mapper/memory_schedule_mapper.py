from datetime import date
from threading import RLock

from app.mapper.base_schedule_mapper import BaseScheduleMapper
from app.model.meeting_entry import MeetingEntry


class MemoryScheduleMapper(BaseScheduleMapper):
    """Process-local storage used by the MVP."""

    def __init__(self) -> None:
        self._entries: dict[str, MeetingEntry] = {}
        self._lock = RLock()

    def save(self, entry: MeetingEntry) -> MeetingEntry:
        with self._lock:
            self._entries[entry.id] = entry.model_copy(deep=True)
            return self._entries[entry.id].model_copy(deep=True)

    def find_by_id(self, entry_id: str) -> MeetingEntry | None:
        with self._lock:
            entry = self._entries.get(entry_id)
            return entry.model_copy(deep=True) if entry else None

    def find_by_date(self, date: str) -> list[MeetingEntry]:
        with self._lock:
            entries = [entry for entry in self._entries.values() if entry.date == date]
        return [entry.model_copy(deep=True) for entry in sorted(entries, key=lambda item: item.start_time)]

    def list_all(self) -> list[MeetingEntry]:
        with self._lock:
            entries = list(self._entries.values())
        return [entry.model_copy(deep=True) for entry in sorted(entries, key=lambda item: item.start_time)]

    def find_duplicate(self, entry: MeetingEntry) -> MeetingEntry | None:
        with self._lock:
            for existing in self._entries.values():
                if _is_same_meeting(existing, entry):
                    return existing.model_copy(deep=True)
        return None

    def find_by_source_id(self, source_id: str) -> MeetingEntry | None:
        with self._lock:
            for entry in self._entries.values():
                if entry.source_id == source_id:
                    return entry.model_copy(deep=True)
        return None

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            return self._entries.pop(entry_id, None) is not None


def _is_same_meeting(left: MeetingEntry, right: MeetingEntry) -> bool:
    """Compare the stable meeting fields without relying on generated IDs."""
    return (
        left.kind == right.kind
        and left.start_time == right.start_time
        and left.end_time == right.end_time
        and left.subject.strip().casefold() == right.subject.strip().casefold()
        and left.platform.strip().casefold() == right.platform.strip().casefold()
        and _normalize_text(left.room_number) == _normalize_text(right.room_number)
        and _normalize_text(left.meeting_url) == _normalize_text(right.meeting_url)
    )


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().rstrip("/").casefold()
