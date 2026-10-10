"""Persistence boundary for a user's interview experiences and questions."""

from abc import ABC, abstractmethod
from datetime import datetime

from app.model.interview_experience import InterviewExperience, InterviewQuestion


class BaseInterviewExperienceMapper(ABC):
    @abstractmethod
    def save_experience(self, experience: InterviewExperience) -> InterviewExperience: ...

    @abstractmethod
    def find_experience(self, experience_id: str, owner_id: str) -> InterviewExperience | None: ...

    @abstractmethod
    def list_experiences(self, owner_id: str) -> list[InterviewExperience]: ...

    @abstractmethod
    def list_public_experiences(self) -> list[InterviewExperience]: ...

    @abstractmethod
    def find_public_experience(self, experience_id: str) -> InterviewExperience | None: ...

    @abstractmethod
    def list_public_questions(self, experience_id: str) -> list[InterviewQuestion]: ...

    @abstractmethod
    def count_public_questions(self) -> dict[str, int]: ...

    @abstractmethod
    def count_questions_by_experience(self, owner_id: str) -> dict[str, int]: ...

    @abstractmethod
    def delete_experience(self, experience_id: str, owner_id: str) -> bool: ...

    @abstractmethod
    def save_question(self, question: InterviewQuestion, owner_id: str) -> InterviewQuestion: ...

    @abstractmethod
    def find_question(self, question_id: str, owner_id: str) -> InterviewQuestion | None: ...

    @abstractmethod
    def list_questions(self, experience_id: str, owner_id: str) -> list[InterviewQuestion]: ...

    @abstractmethod
    def delete_questions(self, question_ids: list[str], owner_id: str) -> None: ...

    @abstractmethod
    def replace_draft(self, experience_id: str, owner_id: str, expected_updated_at: datetime,
                      questions: list[InterviewQuestion], updated_at: datetime,
                      category_minutes: dict[str, int] | None = None,
                      total_minutes: int | None = None,
                      feeling: str | None = None,
                      raw_text_draft: str | None = None) -> InterviewExperience: ...
