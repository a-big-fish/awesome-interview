from threading import RLock

from app.mapper.base_personal_event_mapper import BasePersonalEventMapper
from app.model.personal_event import PersonalEvent


class MemoryPersonalEventMapper(BasePersonalEventMapper):
    def __init__(self) -> None:
        self._events: dict[str, PersonalEvent] = {}
        self._lock = RLock()

    def save(self, event: PersonalEvent) -> PersonalEvent:
        with self._lock:
            self._events[event.id] = event.model_copy(deep=True)
            return self._events[event.id].model_copy(deep=True)

    def find_by_id(self, event_id: str, owner_id: str = "local") -> PersonalEvent | None:
        with self._lock:
            event = self._events.get(event_id)
            return event.model_copy(deep=True) if event and event.owner_id == owner_id else None

    def list_all(self, owner_id: str = "local") -> list[PersonalEvent]:
        with self._lock:
            events = [event for event in self._events.values() if event.owner_id == owner_id]
        return [event.model_copy(deep=True) for event in sorted(events, key=lambda item: item.start_at)]

    def delete(self, event_id: str, owner_id: str = "local") -> bool:
        with self._lock:
            if event_id not in self._events or self._events[event_id].owner_id != owner_id:
                return False
            del self._events[event_id]
            return True
