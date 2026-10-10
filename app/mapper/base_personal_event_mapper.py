from abc import ABC, abstractmethod

from app.model.personal_event import PersonalEvent


class BasePersonalEventMapper(ABC):
    @abstractmethod
    def save(self, event: PersonalEvent) -> PersonalEvent:
        """Create or update an event."""

    @abstractmethod
    def find_by_id(self, event_id: str, owner_id: str = "local") -> PersonalEvent | None:
        """Find one event owned by the given profile."""

    @abstractmethod
    def list_all(self, owner_id: str = "local") -> list[PersonalEvent]:
        """List the owner's events ordered by start time."""

    @abstractmethod
    def delete(self, event_id: str, owner_id: str = "local") -> bool:
        """Delete an event owned by the given profile."""
