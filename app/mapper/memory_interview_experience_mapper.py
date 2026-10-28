from threading import RLock
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.mapper.base_interview_experience_mapper import BaseInterviewExperienceMapper
from app.model.interview_experience import InterviewExperience, InterviewQuestion


class MemoryInterviewExperienceMapper(BaseInterviewExperienceMapper):
    def __init__(self) -> None:
        self._experiences: dict[str, InterviewExperience] = {}
        self._questions: dict[str, InterviewQuestion] = {}
        self._lock = RLock()

    def save_experience(self, experience: InterviewExperience) -> InterviewExperience:
        with self._lock:
            self._experiences[experience.id] = experience.model_copy(deep=True)
            return experience.model_copy(deep=True)

    def find_experience(self, experience_id: str, owner_id: str) -> InterviewExperience | None:
        with self._lock:
            item = self._experiences.get(experience_id)
            return item.model_copy(deep=True) if item and item.owner_id == owner_id else None

    def list_experiences(self, owner_id: str) -> list[InterviewExperience]:
        with self._lock:
            items = [item.model_copy(deep=True) for item in self._experiences.values()
                     if item.owner_id == owner_id]
        return sorted(items, key=lambda item: (item.updated_at, item.id), reverse=True)

    def experience_counts_by_day(self) -> dict[date, tuple[int, int]]:
        """Aggregate all saved experiences, including private and draft entries."""
        counts: dict[date, tuple[int, int]] = {}
        with self._lock:
            for item in self._experiences.values():
                day = item.created_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
                public, private = counts.get(day, (0, 0))
                counts[day] = (public + int(item.is_public), private + int(not item.is_public))
        return counts

    def list_public_experiences(self) -> list[InterviewExperience]:
        with self._lock:
            return [item.model_copy(deep=True) for item in self._experiences.values()
                    if item.is_public]

    def list_public_batch(self, company: str, order: str, offset: int,
                          limit: int) -> tuple[list[dict], int]:
        with self._lock:
            counts = self.count_public_questions()
            entries = [{"experience": item.model_copy(deep=True),
                        "question_count": counts.get(item.id, 0)}
                       for item in self._experiences.values()
                       if item.is_public and (item.company or "").strip()
                       and (not company or company.casefold() in item.company.casefold())
                       and (counts.get(item.id, 0) or (item.feeling or "").strip())]
        dated = [row for row in entries if row["experience"].interviewed_at]
        undated = [row for row in entries if not row["experience"].interviewed_at]
        dated.sort(key=lambda row: (row["experience"].interviewed_at, row["experience"].id),
                   reverse=order != "oldest")
        undated.sort(key=lambda row: row["experience"].id, reverse=order != "oldest")
        entries = dated + undated
        result = entries[offset:offset + limit]
        for row in result:
            item = row["experience"]
            item.raw_text_draft = ""
            item.feeling = item.feeling[:111] if item.feeling else None
        return result, len(entries)

    def find_public_experience(self, experience_id: str) -> InterviewExperience | None:
        with self._lock:
            item = self._experiences.get(experience_id)
            return item.model_copy(deep=True) if item and item.is_public else None

    def list_public_questions(self, experience_id: str) -> list[InterviewQuestion]:
        with self._lock:
            experience = self._experiences.get(experience_id)
            if not experience or not experience.is_public:
                return []
            return sorted([item.model_copy(deep=True) for item in self._questions.values()
                           if item.experience_id == experience_id],
                          key=lambda item: (item.asked_order, item.id))

    def count_public_questions(self) -> dict[str, int]:
        with self._lock:
            public_ids = {item.id for item in self._experiences.values() if item.is_public}
            counts: dict[str, int] = {}
            for item in self._questions.values():
                if item.experience_id in public_ids:
                    counts[item.experience_id] = counts.get(item.experience_id, 0) + 1
            return counts

    def count_questions_by_experience(self, owner_id: str) -> dict[str, int]:
        with self._lock:
            owned = {item.id for item in self._experiences.values() if item.owner_id == owner_id}
            counts: dict[str, int] = {}
            for item in self._questions.values():
                if item.experience_id in owned:
                    counts[item.experience_id] = counts.get(item.experience_id, 0) + 1
            return counts

    def delete_experience(self, experience_id: str, owner_id: str) -> bool:
        with self._lock:
            if not self.find_experience(experience_id, owner_id):
                return False
            del self._experiences[experience_id]
            self._questions = {key: item for key, item in self._questions.items()
                               if item.experience_id != experience_id}
            return True

    def save_question(self, question: InterviewQuestion, owner_id: str) -> InterviewQuestion:
        with self._lock:
            if not self.find_experience(question.experience_id, owner_id):
                raise LookupError("面经不存在")
            self._questions[question.id] = question.model_copy(deep=True)
            return question.model_copy(deep=True)

    def find_question(self, question_id: str, owner_id: str) -> InterviewQuestion | None:
        with self._lock:
            item = self._questions.get(question_id)
            return item.model_copy(deep=True) if item and self.find_experience(
                item.experience_id, owner_id) else None

    def list_questions(self, experience_id: str, owner_id: str) -> list[InterviewQuestion]:
        with self._lock:
            if not self.find_experience(experience_id, owner_id):
                return []
            items = [item.model_copy(deep=True) for item in self._questions.values()
                     if item.experience_id == experience_id]
        return sorted(items, key=lambda item: (item.asked_order, item.id))

    def delete_questions(self, question_ids: list[str], owner_id: str) -> None:
        with self._lock:
            for question_id in question_ids:
                if self.find_question(question_id, owner_id):
                    del self._questions[question_id]

    def replace_draft(self, experience_id: str, owner_id: str, expected_updated_at: datetime,
                      questions: list[InterviewQuestion], updated_at: datetime,
                      category_minutes: dict[str, int] | None = None,
                      total_minutes: int | None = None,
                      feeling: str | None = None,
                      raw_text_draft: str | None = None) -> InterviewExperience:
        with self._lock:
            experience = self._experiences.get(experience_id)
            if not experience or experience.owner_id != owner_id:
                raise LookupError("面经不存在")
            if experience.updated_at != expected_updated_at:
                raise RuntimeError("面经已在其他页面修改，请刷新后核对草稿")
            self._questions = {key: item for key, item in self._questions.items()
                               if item.experience_id != experience_id}
            self._questions.update({item.id: item.model_copy(deep=True) for item in questions})
            if category_minutes is not None:
                experience.category_minutes = category_minutes.copy()
                experience.total_minutes = total_minutes
            if feeling is not None:
                experience.feeling = feeling.strip() or None
            if raw_text_draft is not None:
                experience.raw_text_draft = raw_text_draft
            experience.updated_at = updated_at
            self._experiences[experience_id] = experience.model_copy(deep=True)
            return experience.model_copy(deep=True)
