from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.mapper.base_resume_file_storage import ResumeFileStorage
from interviewschedule.utils.time_utils import now as default_now


class S3CompatibleResumeFileStorage(ResumeFileStorage):
    """Resume file storage for S3-compatible RustFS and MinIO services."""

    provider_name = "s3-compatible"

    def __init__(
        self,
        settings: Settings | None = None,
        client: Any | None = None,
        ensure_bucket: bool = True,
        now_factory: Callable[[], datetime] = default_now,
    ) -> None:
        self.settings = settings
        self.now_factory = now_factory
        if client is not None:
            self._client = client
        else:
            if not settings:
                raise RuntimeError(f"{self.provider_name} settings are required")
            endpoint_url = self._setting("endpoint_url")
            access_key_id = self._setting("access_key_id")
            secret_access_key = self._setting("secret_access_key")
            if not endpoint_url:
                raise RuntimeError(
                    f"{self.provider_name.upper()}_ENDPOINT_URL is required"
                )
            if not access_key_id:
                raise RuntimeError(
                    f"{self.provider_name.upper()}_ACCESS_KEY_ID is required"
                )
            if not secret_access_key:
                raise RuntimeError(
                    f"{self.provider_name.upper()}_SECRET_ACCESS_KEY is required"
                )
            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                config=Config(signature_version="s3v4"),
                region_name=self._setting("region_name"),
            )
        self.bucket_name = (
            self._setting("bucket_name") if settings else "interview-schedule"
        )
        if ensure_bucket:
            self._ensure_bucket()

    def save_pdf(self, content: bytes, file_name: str, resume_id: str) -> str:
        suffix = Path(file_name).suffix.lower() or ".pdf"
        storage_key = self._storage_key("resumes", resume_id, f"{resume_id}{suffix}")
        self._upload(content, storage_key, "application/pdf")
        return storage_key

    def read_pdf(self, storage_key: str) -> bytes:
        return self._read(storage_key)

    def save_image(self, content: bytes, resume_id: str, image_id: str) -> str:
        storage_key = self._storage_key(
            "resume_images",
            resume_id,
            f"{image_id}.png",
            nested_resume_id=True,
        )
        self._upload(content, storage_key, "image/png")
        return storage_key

    def read_image(self, storage_key: str) -> bytes:
        return self._read(storage_key)

    def save_text(self, content: str, resume_id: str) -> str:
        storage_key = self._storage_key(
            "resume_info",
            resume_id,
            f"{resume_id}.txt",
        )
        self._upload(content.encode("utf-8"), storage_key, "text/plain")
        return storage_key

    def read_text(self, storage_key: str) -> str:
        try:
            return self._read(storage_key).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Invalid resume text encoding: {storage_key}") from exc

    def _storage_key(
        self,
        artifact_type: str,
        resume_id: str,
        file_name: str,
        *,
        nested_resume_id: bool = False,
    ) -> str:
        year_month = self.now_factory().strftime("%Y/%m")
        if nested_resume_id:
            return f"{artifact_type}/{year_month}/{resume_id}/{file_name}"
        return f"{artifact_type}/{year_month}/{file_name}"

    def _upload(self, content: bytes, storage_key: str, content_type: str) -> None:
        # Resume files are small. Use the ordinary transfer API without multipart
        # threads, while avoiding a persistent temporary file inside the app.
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "upload-file"
            temp_path.write_bytes(content)
            self._client.upload_file(
                str(temp_path),
                self.bucket_name,
                storage_key,
                ExtraArgs={"ContentType": content_type},
            )

    def _read(self, storage_key: str) -> bytes:
        from io import BytesIO

        buffer = BytesIO()
        try:
            self._client.download_fileobj(self.bucket_name, storage_key, buffer)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            if error.get("Code") in {"404", "NoSuchKey", "NotFound"}:
                raise FileNotFoundError(storage_key) from exc
            raise
        return buffer.getvalue()

    def _setting(self, suffix: str) -> str:
        if not self.settings:
            raise RuntimeError(f"{self.provider_name} settings are required")
        return getattr(self.settings, f"{self.provider_name}_{suffix}")

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket_name)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            if error.get("Code") not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self._client.create_bucket(Bucket=self.bucket_name)


class RustFSResumeFileStorage(S3CompatibleResumeFileStorage):
    """RustFS adapter using its S3-compatible API."""

    provider_name = "rustfs"


class MinIOResumeFileStorage(S3CompatibleResumeFileStorage):
    """MinIO adapter using the same S3-compatible storage boundary."""

    provider_name = "minio"
