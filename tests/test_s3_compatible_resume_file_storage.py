from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.mapper.s3_compatible_resume_file_storage import (
    MinIOResumeFileStorage,
    RustFSResumeFileStorage,
)


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.uploaded = []
        self.head_error = None

    def head_bucket(self, Bucket):
        if self.head_error:
            raise self.head_error

    def create_bucket(self, Bucket):
        self.created_bucket = Bucket

    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):
        self.uploaded.append((Bucket, Key, ExtraArgs))
        self.objects[Key] = (Path(Filename).read_bytes(), ExtraArgs)

    def download_fileobj(self, Bucket, Key, Fileobj):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        Fileobj.write(self.objects[Key][0])


def rustfs_settings():
    return Settings(
        _env_file=None,
        storage_backend="rustfs",
        rustfs_endpoint_url="http://127.0.0.1:9007",
        rustfs_access_key_id="test-user",
        rustfs_secret_access_key="test-password",
        rustfs_region_name="us-east-1",
        rustfs_bucket_name="interview-schedule",
    )


def fixed_now():
    return datetime(2026, 9, 14, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_rustfs_storage_uses_month_prefixes_and_upload_file():
    client = FakeS3Client()
    storage = RustFSResumeFileStorage(
        settings=rustfs_settings(),
        client=client,
        ensure_bucket=False,
        now_factory=fixed_now,
    )

    pdf_key = storage.save_pdf(b"pdf-bytes", "Zhang San.pdf", "resume-1")
    image_key = storage.save_image(b"png-bytes", "resume-1", "1-1")
    text_key = storage.save_text("resume text", "resume-1")

    assert pdf_key == "resumes/2026/09/resume-1.pdf"
    assert image_key == "resume_images/2026/09/resume-1/1-1.png"
    assert text_key == "resume_info/2026/09/resume-1.txt"
    assert len(client.uploaded) == 3
    assert all(bucket == "interview-schedule" for bucket, _, _ in client.uploaded)
    assert client.uploaded[0][2] == {"ContentType": "application/pdf"}
    assert storage.read_pdf(pdf_key) == b"pdf-bytes"
    assert storage.read_image(image_key) == b"png-bytes"
    assert storage.read_text(text_key) == "resume text"


def test_rustfs_storage_creates_missing_bucket():
    client = FakeS3Client()
    client.head_error = ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    RustFSResumeFileStorage(
        settings=rustfs_settings(),
        client=client,
        now_factory=fixed_now,
    )

    assert client.created_bucket == "interview-schedule"


def test_rustfs_storage_wraps_missing_object():
    storage = RustFSResumeFileStorage(
        settings=rustfs_settings(),
        client=FakeS3Client(),
        ensure_bucket=False,
        now_factory=fixed_now,
    )

    with pytest.raises(FileNotFoundError):
        storage.read_pdf("resumes/2026/09/missing.pdf")


def test_minio_storage_uses_same_storage_boundary():
    settings = Settings(
        _env_file=None,
        storage_backend="minio",
        minio_endpoint_url="http://127.0.0.1:9000",
        minio_access_key_id="test-user",
        minio_secret_access_key="test-password",
        minio_bucket_name="interview-schedule",
    )
    storage = MinIOResumeFileStorage(
        settings=settings,
        client=FakeS3Client(),
        ensure_bucket=False,
        now_factory=fixed_now,
    )

    key = storage.save_pdf(b"pdf-bytes", "resume.pdf", "resume-1")

    assert key == "resumes/2026/09/resume-1.pdf"
