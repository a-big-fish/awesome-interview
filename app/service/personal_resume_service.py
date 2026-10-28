"""Read the current resume version without initializing object/file storage."""

from app.mapper.base_my_resume_mapper import BaseMyResumeMapper
from app.mapper.base_resume_mapper import BaseResumeMapper


class PersonalResumeStateService:
    def __init__(self, profiles: BaseMyResumeMapper, resumes: BaseResumeMapper, owner_id: str):
        self.profiles, self.resumes, self.owner_id = profiles, resumes, owner_id

    def current(self) -> dict | None:
        profile = self.profiles.get("default" if self.owner_id == "local" else self.owner_id)
        resume = self.resumes.find_summary(profile.resume_id) if profile else None
        if not resume or resume.owner_id != self.owner_id:
            return None
        return {"id": resume.id, "file_name": resume.file_name,
                "version": f"{resume.id}:{profile.updated_at.isoformat()}",
                "pdf_url": f"/resumes/{resume.id}/pdf"}
