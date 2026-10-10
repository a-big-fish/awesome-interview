from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class ResumeImage(BaseModel):
    image_id: str
    page_number: int
    file_path: str
    width: int | None = None
    height: int | None = None


class Resume(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    owner_id: str = "local"
    file_name: str
    pdf_path: str
    text_path: str | None = None
    page_count: int = 0
    candidate_name: str | None = None
    email: str | None = None
    phone: str | None = None
    raw_text: str = ""
    images: list[ResumeImage] = Field(default_factory=list)
    candidate_photo_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
