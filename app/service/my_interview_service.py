from app.controller.schema.schedule_dto import MeetingEntryCreateDTO
from app.core.exceptions import MyResumeNotFoundError
from app.mapper.base_my_resume_mapper import BaseMyResumeMapper
from app.mapper.base_resume_mapper import BaseResumeMapper
from app.mapper.base_schedule_mapper import BaseScheduleMapper
from app.model.enums import MeetingSource
from app.model.meeting_entry import MeetingEntry
from app.model.my_resume_profile import MyResumeProfile
from app.model.resume import Resume
from app.service.schedule_service import ScheduleService


class MyInterviewService:
    """Business orchestration for the user's own interview workspace."""

    def __init__(
        self,
        schedule_mapper: BaseScheduleMapper,
        resume_mapper: BaseResumeMapper,
        profile_mapper: BaseMyResumeMapper,
    ) -> None:
        self.schedule_mapper = schedule_mapper
        self.resume_mapper = resume_mapper
        self.profile_mapper = profile_mapper

    def get_resume(self) -> Resume | None:
        """Return the resume associated with the current own profile."""
        profile = self.profile_mapper.get()
        return self.resume_mapper.find_by_id(profile.resume_id) if profile else None

    def save_resume(self, resume: Resume) -> Resume:
        """Persist or replace the own-resume profile after parsing."""
        self.profile_mapper.save(MyResumeProfile(resume_id=resume.id))
        return resume

    def create_from_invitation(
        self,
        dto: MeetingEntryCreateDTO,
        uploaded_resume: Resume | None = None,
    ) -> MeetingEntry:
        """Create a personal interview, optionally using a newly parsed resume."""
        if uploaded_resume:
            self.save_resume(uploaded_resume)
        profile = self.profile_mapper.get()
        if not profile:
            raise MyResumeNotFoundError("请先上传我的简历")
        dto.source = MeetingSource.PERSONAL.value
        dto.resume_id = profile.resume_id
        return ScheduleService(schedule_mapper=self.schedule_mapper).create_from_invitation(dto)

    def list_entries(self) -> list[MeetingEntry]:
        """Return personal interviews sorted by start time."""
        return sorted(
            (entry for entry in self.schedule_mapper.list_all() if entry.source == MeetingSource.PERSONAL.value),
            key=lambda entry: entry.start_time,
        )
