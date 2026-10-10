from pydantic import BaseModel, ConfigDict

from app.model.resume import Resume


class ResumeImageVO(BaseModel):
    image_id: str
    page_number: int
    file_path: str
    width: int | None = None
    height: int | None = None


class ResumeVO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_name: str
    page_count: int
    candidate_name: str | None = None
    email: str | None = None
    phone: str | None = None
    raw_text: str
    images: list[ResumeImageVO] = []
    candidate_photo_id: str | None = None

    @classmethod
    def from_domain(cls, resume: Resume) -> "ResumeVO":
        return cls(
            id=resume.id,
            file_name=resume.file_name,
            page_count=resume.page_count,
            candidate_name=resume.candidate_name,
            email=resume.email,
            phone=resume.phone,
            raw_text=resume.raw_text,
            images=[ResumeImageVO.model_validate(image.model_dump()) for image in resume.images],
            candidate_photo_id=resume.candidate_photo_id,
        )
