from abc import ABC, abstractmethod

from app.model.my_resume_profile import MyResumeProfile


class BaseMyResumeMapper(ABC):
    """Storage boundary for the user's own resume profile."""

    @abstractmethod
    def save(self, profile: MyResumeProfile) -> MyResumeProfile:
        raise NotImplementedError

    @abstractmethod
    def get(self, profile_id: str = "default") -> MyResumeProfile | None:
        raise NotImplementedError
