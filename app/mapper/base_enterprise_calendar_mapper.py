from abc import ABC, abstractmethod

from app.model.enterprise_calendar import EnterpriseCalendarSettings


class BaseEnterpriseCalendarMapper(ABC):
    @abstractmethod
    def get(self) -> EnterpriseCalendarSettings | None:
        """Load the single enterprise calendar configuration."""

    @abstractmethod
    def save(self, settings: EnterpriseCalendarSettings) -> EnterpriseCalendarSettings:
        """Persist the enterprise calendar configuration."""
