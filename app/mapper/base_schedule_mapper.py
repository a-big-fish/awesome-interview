from abc import ABC, abstractmethod

from app.model.meeting_entry import MeetingEntry


class BaseScheduleMapper(ABC):
    """Storage boundary for schedule entries."""

    @abstractmethod
    def save(self, entry: MeetingEntry) -> MeetingEntry:
        raise NotImplementedError

    @abstractmethod
    def find_by_id(self, entry_id: str) -> MeetingEntry | None:
        raise NotImplementedError

    @abstractmethod
    def find_by_date(self, date: str) -> list[MeetingEntry]:
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> list[MeetingEntry]:
        raise NotImplementedError

    @abstractmethod
    def find_duplicate(self, entry: MeetingEntry) -> MeetingEntry | None:
        """Return an existing entry with the same meeting identity."""
        raise NotImplementedError

    @abstractmethod
    def find_by_source_id(self, source_id: str) -> MeetingEntry | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, entry_id: str) -> bool:
        raise NotImplementedError
