from threading import RLock

from app.mapper.base_resume_mapper import BaseResumeMapper
from app.model.resume import Resume


class MemoryResumeMapper(BaseResumeMapper):
    """Process-local resume metadata storage."""

    def __init__(self) -> None:
        self._resumes: dict[str, Resume] = {}
        self._lock = RLock()

    def save(self, resume: Resume) -> Resume:
        with self._lock:
            self._resumes[resume.id] = resume.model_copy(deep=True)
            return self._resumes[resume.id].model_copy(deep=True)

    def find_by_id(self, resume_id: str) -> Resume | None:
        with self._lock:
            resume = self._resumes.get(resume_id)
            return resume.model_copy(deep=True) if resume else None
