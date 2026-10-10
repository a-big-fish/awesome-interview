"""Rules for personal interview notes and their follow-up questions."""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.mapper.base_interview_experience_mapper import BaseInterviewExperienceMapper
from app.model.interview_experience import (
    CATEGORY_LABELS, InterviewExperience, InterviewQuestion, QuestionCategory,
)
from app.service.personal_schedule_service import PersonalScheduleService


def _now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


class InterviewExperienceService:
    def __init__(self, mapper: BaseInterviewExperienceMapper,
                 schedule_service: PersonalScheduleService, owner_id: str) -> None:
        self.mapper = mapper
        self.schedule_service = schedule_service
        self.owner_id = owner_id

    def list_experiences(self) -> list[InterviewExperience]:
        return self.mapper.list_experiences(self.owner_id)

    def list_plaza(self, company: str = "", order: str = "newest",
                   page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        """Return visible, substantive experiences without exposing private fields."""
        candidates = self.mapper.list_public_experiences()
        counts = self.mapper.count_public_questions()
        entries = []
        for item in candidates:
            if not (item.company or "").strip():
                continue
            if company and company.casefold() not in (item.company or "").casefold():
                continue
            count = counts.get(item.id, 0)
            if not count and not (item.feeling or "").strip():
                continue
            entries.append({"experience": item, "question_count": count})
        dated = [entry for entry in entries if entry["experience"].interviewed_at]
        undated = [entry for entry in entries if not entry["experience"].interviewed_at]
        dated.sort(key=lambda entry: (entry["experience"].interviewed_at,
                                      entry["experience"].id), reverse=order != "oldest")
        entries = dated + undated
        start = (max(page, 1) - 1) * page_size
        return entries[start:start + page_size], len(entries)

    def get_public_experience(self, experience_id: str) -> tuple[InterviewExperience, list[InterviewQuestion]] | None:
        """Read a public experience only when it contains saved content."""
        item = self.mapper.find_public_experience(experience_id)
        if not item or not (item.company or "").strip():
            return None
        questions = self.mapper.list_public_questions(experience_id)
        if not questions and not (item.feeling or "").strip():
            return None
        return item, questions

    def count_questions_by_experience(self) -> dict[str, int]:
        return self.mapper.count_questions_by_experience(self.owner_id)

    def get_experience(self, experience_id: str) -> InterviewExperience | None:
        return self.mapper.find_experience(experience_id, self.owner_id)

    def set_visibility(self, experience_id: str, is_public: bool) -> InterviewExperience:
        """Change visibility of one owned experience."""
        experience = self.get_experience(experience_id)
        if not experience:
            raise LookupError("面经不存在")
        experience.is_public = is_public
        experience.updated_at = _now()
        return self.mapper.save_experience(experience)

    def for_event(self, event_id: str) -> list[InterviewExperience]:
        event = self.schedule_service.get_event(event_id)
        if not event or event.type != "interview":
            return []
        return [item for item in self.list_experiences() if item.linked_event_id == event_id]

    def _event(self, event_id: str | None):
        if not event_id:
            return None
        event = self.schedule_service.get_event(event_id)
        if not event or event.type != "interview":
            raise ValueError("只能关联自己的面试日程")
        return event

    def create_experience(self, title: str, linked_event_id: str | None = None,
                          company: str | None = None, position: str | None = None,
                          interviewed_at: datetime | None = None,
                          is_public: bool = True, interview_round: str | None = None) -> InterviewExperience:
        event = self._event(linked_event_id)
        cleaned = title.strip()
        if not cleaned:
            raise ValueError("请填写面经标题")
        experience = InterviewExperience(
            owner_id=self.owner_id, title=cleaned, linked_event_id=linked_event_id or None,
            company=company.strip() or None if company else None,
            position=(position.strip() or None if position else None) or (event.position if event else None),
            interviewed_at=interviewed_at or (event.start_at if event else None),
            is_public=is_public, interview_round=interview_round or None,
        )
        return self.mapper.save_experience(experience)

    def update_experience(self, experience_id: str, *, title: str,
                          linked_event_id: str | None, company: str | None,
                          position: str | None,
                          interviewed_at: datetime | None = None,
                          is_public: bool | None = None,
                          interview_round: str | None = None) -> InterviewExperience:
        current = self.get_experience(experience_id)
        if not current:
            raise LookupError("面经不存在")
        event = self._event(linked_event_id)
        cleaned = title.strip()
        if not cleaned:
            raise ValueError("请填写面经标题")
        current.title = cleaned
        current.linked_event_id = linked_event_id or None
        current.company = company.strip() or None if company else None
        current.position = position.strip() or None if position else None
        current.interviewed_at = interviewed_at
        if is_public is not None:
            current.is_public = is_public
        current.interview_round = interview_round or None
        if event:
            current.interviewed_at = event.start_at
            if not current.position:
                current.position = event.position
        current.updated_at = _now()
        return self.mapper.save_experience(InterviewExperience.model_validate(current.model_dump()))

    def delete_experience(self, experience_id: str) -> bool:
        return self.mapper.delete_experience(experience_id, self.owner_id)

    def list_questions(self, experience_id: str) -> list[InterviewQuestion]:
        if not self.get_experience(experience_id):
            raise LookupError("面经不存在")
        return self.mapper.list_questions(experience_id, self.owner_id)

    def save_draft(self, experience_id: str, expected_updated_at: datetime,
                   items: list[dict], category_minutes: dict | None = None,
                   total_minutes: int | None = None,
                   feeling: str | None = None,
                   raw_text_draft: str | None = None) -> tuple[InterviewExperience, list[InterviewQuestion]]:
        """Validate one complete draft and replace its questions in a single transaction."""
        experience = self.get_experience(experience_id)
        if not experience:
            raise LookupError("面经不存在")
        if len(items) > 500:
            raise ValueError("一份面经最多记录 500 道问题")
        if feeling is not None and (not isinstance(feeling, str) or len(feeling) > 20000):
            raise ValueError("面试感受不能超过 20000 字")
        if raw_text_draft is not None and (not isinstance(raw_text_draft, str) or len(raw_text_draft) > 100000):
            raise ValueError("解析原文不能超过 100000 字")
        normalized_minutes = None
        if category_minutes is not None:
            if not isinstance(category_minutes, dict):
                raise ValueError("模块用时格式无效")
            normalized_minutes = {}
            for key, minutes in category_minutes.items():
                if key not in CATEGORY_LABELS or type(minutes) is not int or not 0 <= minutes <= 1440:
                    raise ValueError("模块用时必须为 0 到 1440 分钟")
                normalized_minutes[key] = minutes
            if total_minutes is not None and (type(total_minutes) is not int or not 0 <= total_minutes <= 1440):
                raise ValueError("总用时必须为 0 到 1440 分钟")
        old = {item.id: item for item in self.mapper.list_questions(experience_id, self.owner_id)}
        now = _now()
        max_order = max((item.asked_order for item in old.values()), default=0)
        seen: set[str] = set()
        questions: list[InterviewQuestion] = []
        for raw in items:
            if not isinstance(raw, dict):
                raise ValueError("问题格式无效")
            item_id = raw.get("id")
            try:
                UUID(str(item_id))
            except (ValueError, TypeError) as exc:
                raise ValueError("问题编号无效") from exc
            if item_id in seen:
                raise ValueError("问题编号重复")
            seen.add(item_id)
            original = old.get(item_id)
            parent_id = raw.get("parent_question_id") or None
            if original and original.parent_question_id != parent_id:
                raise ValueError("不能改变已有问题的上级")
            if not original:
                max_order += 1
            question = InterviewQuestion(
                id=item_id, experience_id=experience_id, parent_question_id=parent_id,
                category=raw.get("category"),
                asked_order=original.asked_order if original else max_order,
                sibling_order=raw.get("sibling_order") or 1,
                question_text=str(raw.get("question_text") or "").strip(),
                on_site_answer=str(raw.get("on_site_answer") or "").strip() or None,
                review_answer=str(raw.get("review_answer") or "").strip() or None,
                interviewer_answer=str(raw.get("interviewer_answer") or "").strip() or None,
                created_at=original.created_at if original else now,
                updated_at=now if not original or any(
                    getattr(original, key) != (str(raw.get(key) or "").strip() or None)
                    for key in ("question_text", "on_site_answer", "review_answer", "interviewer_answer")
                ) else original.updated_at,
            )
            questions.append(question)
        by_id = {item.id: item for item in questions}
        for item in questions:
            visited = {item.id}
            parent_id = item.parent_question_id
            depth = 0
            while parent_id:
                parent = by_id.get(parent_id)
                if not parent or parent_id in visited:
                    raise ValueError("追问层级或上级问题无效")
                visited.add(parent_id)
                depth += 1
                if depth >= 20:
                    raise ValueError("追问层级最多为 20 级")
                parent_id = parent.parent_question_id
            if item.parent_question_id:
                ancestor = by_id[item.parent_question_id]
                while ancestor.parent_question_id:
                    ancestor = by_id[ancestor.parent_question_id]
                item.category = ancestor.category
            if item.category == "reverse":
                item.on_site_answer = None
                item.review_answer = None
            else:
                item.interviewer_answer = None
        groups: dict[str | None, list[InterviewQuestion]] = {}
        for item in questions:
            groups.setdefault(item.parent_question_id, []).append(item)
        for group in groups.values():
            group.sort(key=lambda item: (item.sibling_order, item.asked_order))
            for index, item in enumerate(group, 1):
                item.sibling_order = index
        saved = self.mapper.replace_draft(
            experience_id, self.owner_id, expected_updated_at, questions, now,
            normalized_minutes, total_minutes, feeling, raw_text_draft)
        return saved, sorted(questions, key=lambda item: (item.asked_order, item.id))

    def add_question(self, experience_id: str, question_text: str,
                     category: QuestionCategory, parent_question_id: str | None = None,
                     on_site_answer: str | None = None,
                     review_answer: str | None = None,
                     interviewer_answer: str | None = None) -> InterviewQuestion:
        experience = self.get_experience(experience_id)
        if not experience:
            raise LookupError("面经不存在")
        cleaned = question_text.strip()
        if not cleaned:
            raise ValueError("请填写问题")
        if category not in CATEGORY_LABELS:
            raise ValueError("问题分类无效")
        questions = self.list_questions(experience_id)
        if parent_question_id:
            parent = next((item for item in questions if item.id == parent_question_id), None)
            if not parent:
                raise ValueError("追问的上级问题不存在")
            category = parent.category
            depth = 1
            ancestor = parent
            while ancestor.parent_question_id:
                depth += 1
                if depth >= 20:
                    raise ValueError("追问层级最多为 20 级")
                ancestor = next(item for item in questions
                                if item.id == ancestor.parent_question_id)
        siblings = [item for item in questions if item.parent_question_id == parent_question_id]
        question = InterviewQuestion(
            experience_id=experience_id, parent_question_id=parent_question_id or None,
            category=category, asked_order=max((item.asked_order for item in questions), default=0) + 1,
            sibling_order=max((item.sibling_order or item.asked_order for item in siblings),
                              default=0) + 1,
            question_text=cleaned,
            on_site_answer=on_site_answer.strip() or None if on_site_answer and category != "reverse" else None,
            review_answer=review_answer.strip() or None if review_answer and category != "reverse" else None,
            interviewer_answer=interviewer_answer.strip() or None if interviewer_answer and category == "reverse" else None,
        )
        saved = self.mapper.save_question(question, self.owner_id)
        experience.updated_at = _now()
        self.mapper.save_experience(experience)
        return saved

    def update_question(self, experience_id: str, question_id: str, *, question_text: str,
                        category: QuestionCategory, on_site_answer: str | None,
                        review_answer: str | None,
                        interviewer_answer: str | None = None) -> InterviewQuestion:
        question = self.mapper.find_question(question_id, self.owner_id)
        if not question or question.experience_id != experience_id:
            raise LookupError("问题不存在")
        cleaned = question_text.strip()
        if not cleaned:
            raise ValueError("请填写问题")
        if category not in CATEGORY_LABELS:
            raise ValueError("问题分类无效")
        questions = self.list_questions(experience_id)
        if question.parent_question_id:
            parent = next(item for item in questions if item.id == question.parent_question_id)
            category = parent.category
        question.question_text = cleaned
        question.on_site_answer = on_site_answer.strip() or None if on_site_answer and category != "reverse" else None
        question.review_answer = review_answer.strip() or None if review_answer and category != "reverse" else None
        question.interviewer_answer = interviewer_answer.strip() or None if interviewer_answer and category == "reverse" else None
        question.updated_at = _now()
        question.category = category
        question = InterviewQuestion.model_validate(question.model_dump())
        saved = self.mapper.save_question(question, self.owner_id)
        if not question.parent_question_id:
            for child in self._descendants(question.id, questions):
                child.category = category
                if category == "reverse":
                    child.on_site_answer = None
                    child.review_answer = None
                else:
                    child.interviewer_answer = None
                self.mapper.save_question(child, self.owner_id)
        self._touch(experience_id)
        return saved

    def _descendants(self, parent_id: str, questions: list[InterviewQuestion]) -> list[InterviewQuestion]:
        result: list[InterviewQuestion] = []
        pending = [parent_id]
        while pending:
            current_id = pending.pop()
            children = [item for item in questions if item.parent_question_id == current_id]
            result.extend(children)
            pending.extend(item.id for item in children)
        return result

    def delete_question(self, experience_id: str, question_id: str) -> int:
        questions = self.list_questions(experience_id)
        if not any(item.id == question_id for item in questions):
            raise LookupError("问题不存在")
        ids = [question_id, *(item.id for item in self._descendants(question_id, questions))]
        self.mapper.delete_questions(ids, self.owner_id)
        self._touch(experience_id)
        return len(ids)

    def move_question(self, experience_id: str, question_id: str,
                      direction: str) -> None:
        """Reorder siblings without changing their original interview chronology."""
        if direction not in {"up", "down"}:
            raise ValueError("移动方向无效")
        questions = self.list_questions(experience_id)
        current = next((item for item in questions if item.id == question_id), None)
        if not current:
            raise LookupError("问题不存在")
        siblings = sorted(
            (item for item in questions if item.parent_question_id == current.parent_question_id),
            key=lambda item: (item.sibling_order or item.asked_order, item.asked_order),
        )
        position = next(index for index, item in enumerate(siblings) if item.id == question_id)
        target = position + (-1 if direction == "up" else 1)
        if not 0 <= target < len(siblings):
            return
        siblings[position], siblings[target] = siblings[target], siblings[position]
        for index, item in enumerate(siblings, 1):
            item.sibling_order = index
            self.mapper.save_question(item, self.owner_id)
        self._touch(experience_id)

    def _touch(self, experience_id: str) -> None:
        experience = self.get_experience(experience_id)
        if experience:
            experience.updated_at = _now()
            self.mapper.save_experience(experience)

    def numbered_questions(self, experience_id: str) -> list[dict]:
        """Return chronological questions with tree numbers and depth for both views."""
        return self.number_questions(self.list_questions(experience_id))

    @staticmethod
    def number_questions(questions: list[InterviewQuestion]) -> list[dict]:
        """Number a verified question list without reading other private records."""
        siblings: dict[str | None, list[InterviewQuestion]] = {}
        for item in questions:
            siblings.setdefault(item.parent_question_id, []).append(item)
        for group in siblings.values():
            group.sort(key=lambda item: (item.sibling_order or item.asked_order,
                                         item.asked_order))
        numbers: dict[str, str] = {}
        depths: dict[str, int] = {}
        mobility: dict[str, tuple[bool, bool]] = {}
        for group in siblings.values():
            for index, item in enumerate(group):
                mobility[item.id] = (index > 0, index < len(group) - 1)

        def visit(parent_id: str | None, prefix: str, depth: int) -> None:
            for index, item in enumerate(siblings.get(parent_id, []), 1):
                number = f"{prefix}.{index}" if prefix else f"Q{index}"
                numbers[item.id] = number
                depths[item.id] = depth
                visit(item.id, number, depth + 1)

        visit(None, "", 0)
        return [{"question": item, "number": numbers.get(item.id, "Q?"),
                 "depth": depths.get(item.id, 0),
                 "parent_number": numbers.get(item.parent_question_id),
                 "can_move_up": mobility.get(item.id, (False, False))[0],
                 "can_move_down": mobility.get(item.id, (False, False))[1]} for item in questions]

    def tree_questions(self, experience_id: str, category: str) -> list[dict]:
        """Order one category by parent chain while retaining the original asked order."""
        return self.tree_rows(self.numbered_questions(experience_id), category)

    @staticmethod
    def tree_rows(rows: list[dict], category: str) -> list[dict]:
        by_id = {row["question"].id: row for row in rows}

        def path(row: dict) -> tuple[int, ...]:
            parent = by_id.get(row["question"].parent_question_id)
            order = row["question"].sibling_order or row["question"].asked_order
            return (*path(parent), order) if parent else (order,)

        return sorted((row for row in rows if row["question"].category == category), key=path)
