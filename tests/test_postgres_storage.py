import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.mapper.postgres_resume_file_storage import PostgresResumeFileStorage
from app.mapper.postgres_resume_mapper import PostgresResumeMapper
from app.mapper.postgres_schedule_mapper import PostgresScheduleMapper
from app.model.meeting_entry import MeetingEntry
from app.model.resume import Resume, ResumeImage


@pytest.fixture
def postgres_settings() -> Settings:
    settings = Settings(_env_file=".env")
    if settings.storage_backend != "postgres":
        pytest.skip("PostgreSQL storage backend is not configured")
    return settings


def test_postgres_storage_round_trip(postgres_settings):
    schedule_mapper = PostgresScheduleMapper(settings=postgres_settings)
    resume_mapper = PostgresResumeMapper(settings=postgres_settings)
    file_storage = PostgresResumeFileStorage(settings=postgres_settings)
    resume_id = str(uuid.uuid4())
    entry_id = str(uuid.uuid4())
    resume = Resume(
        id=resume_id,
        file_name="postgres-test.pdf",
        pdf_path="unused",
        text_path="unused",
        page_count=1,
        candidate_name="PG Test",
        email="pg-test@example.com",
        phone="13800000000",
        raw_text="postgres integration test",
        images=[
            ResumeImage(
                image_id="1-1",
                page_number=1,
                file_path="unused",
                width=295,
                height=413,
            )
        ],
        created_at=datetime.now(timezone.utc),
    )
    started_at = datetime.now(timezone.utc)
    entry = MeetingEntry(
        id=entry_id,
        candidate_name="PG Test",
        position="Backend",
        subject="PostgreSQL persistence test",
        start_time=started_at,
        end_time=started_at + timedelta(minutes=30),
        resume_id=resume_id,
        created_at=started_at,
    )

    try:
        pdf_key = file_storage.save_pdf(b"pdf-content", resume.file_name, resume.id)
        image_key = file_storage.save_image(b"image-content", resume.id, "1-1")
        text_key = file_storage.save_text(resume.raw_text, resume.id)
        resume.pdf_path = pdf_key
        resume.text_path = text_key
        resume.images[0].file_path = image_key

        saved_resume = resume_mapper.save(resume)
        saved_entry = schedule_mapper.save(entry)

        assert saved_resume.email == "pg-test@example.com"
        assert saved_entry.candidate_name == "PG Test"
        assert file_storage.read_pdf(pdf_key) == b"pdf-content"
        assert file_storage.read_image(image_key) == b"image-content"
        assert file_storage.read_text(text_key) == "postgres integration test"
        assert schedule_mapper.find_by_id(entry_id) is not None
        assert schedule_mapper.find_duplicate(saved_entry)
        assert resume_mapper.find_by_id(resume_id) is not None
        assert entry.id in {item.id for item in schedule_mapper.find_by_date(entry.date)}
        assert entry.id in {item.id for item in schedule_mapper.list_all()}
        assert schedule_mapper.delete(entry_id) is True
    finally:
        schedule_mapper.delete(entry_id)
        with file_storage._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM interview_resume_files WHERE resume_id = %s",
                    (resume_id,),
                )
            connection.commit()
