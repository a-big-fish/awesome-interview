from app.core.config import Settings
from app.mapper.base_resume_file_storage import ResumeFileStorage
from app.mapper.local_resume_file_storage import LocalResumeFileStorage
from app.mapper.postgres_resume_file_storage import PostgresResumeFileStorage
from app.mapper.s3_compatible_resume_file_storage import (
    MinIOResumeFileStorage,
    RustFSResumeFileStorage,
)


def build_resume_file_storage(settings: Settings) -> ResumeFileStorage:
    """Build the configured resume file storage adapter."""
    if settings.storage_backend == "rustfs":
        return RustFSResumeFileStorage(settings=settings)
    if settings.storage_backend == "minio":
        return MinIOResumeFileStorage(settings=settings)
    if settings.storage_backend == "postgres":
        return PostgresResumeFileStorage(settings=settings)
    return LocalResumeFileStorage()
