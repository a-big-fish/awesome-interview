from threading import RLock

from app.mapper.base_enterprise_calendar_mapper import BaseEnterpriseCalendarMapper
from app.model.enterprise_calendar import EnterpriseCalendarSettings


class MemoryEnterpriseCalendarMapper(BaseEnterpriseCalendarMapper):
    def __init__(self) -> None:
        self._settings: EnterpriseCalendarSettings | None = None
        self._lock = RLock()

    def get(self) -> EnterpriseCalendarSettings | None:
        with self._lock:
            return self._settings.model_copy(deep=True) if self._settings else None

    def save(self, settings: EnterpriseCalendarSettings) -> EnterpriseCalendarSettings:
        with self._lock:
            self._settings = settings.model_copy(deep=True)
            return self._settings.model_copy(deep=True)
