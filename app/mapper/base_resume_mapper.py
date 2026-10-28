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

    def find_summary(self, resume_id: str) -> Resume | None:
        resume = self.find_by_id(resume_id)
        return resume.model_copy(update={"raw_text": "", "images": [], "email": None,
                                         "phone": None, "candidate_name": None}) if resume else None
