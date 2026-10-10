from threading import RLock

from app.mapper.base_my_resume_mapper import BaseMyResumeMapper
from app.model.my_resume_profile import MyResumeProfile


class MemoryMyResumeMapper(BaseMyResumeMapper):
    """Process-local storage for the user's own resume profile."""

    def __init__(self) -> None:
        self._profiles: dict[str, MyResumeProfile] = {}
        self._lock = RLock()

    def save(self, profile: MyResumeProfile) -> MyResumeProfile:
        with self._lock:
            self._profiles[profile.id] = profile.model_copy(deep=True)
            return self._profiles[profile.id].model_copy(deep=True)

    def get(self, profile_id: str = "default") -> MyResumeProfile | None:
        with self._lock:
            profile = self._profiles.get(profile_id)
            return profile.model_copy(deep=True) if profile else None
