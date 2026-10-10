from abc import ABC, abstractmethod

from app.model.resume import Resume


class BaseResumeMapper(ABC):
    """Storage boundary for parsed resume metadata."""

    @abstractmethod
    def save(self, resume: Resume) -> Resume:
        raise NotImplementedError

    @abstractmethod
    def find_by_id(self, resume_id: str) -> Resume | None:
        raise NotImplementedError
