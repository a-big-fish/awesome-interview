from pathlib import Path

from app.mapper.base_resume_file_storage import ResumeFileStorage


class LocalResumeFileStorage(ResumeFileStorage):
    """Local filesystem implementation used by the MVP."""

    def __init__(self, root_dir: Path | str = Path("data")) -> None:
        self.root_dir = Path(root_dir)
        self.root_path = self.root_dir.resolve()
        self.pdf_dir = self.root_path / "resumes"
        self.image_dir = self.root_path / "resume_images"
        self.text_dir = self.root_path / "resume_info"

    def save_pdf(self, content: bytes, file_name: str, resume_id: str) -> str:
        suffix = Path(file_name).suffix.lower() or ".pdf"
        path = self.pdf_dir / f"{resume_id}{suffix}"
        self._write(path, content)
        return self._storage_key(path)

    def read_pdf(self, storage_key: str) -> bytes:
        return self._read(storage_key)

    def save_image(self, content: bytes, resume_id: str, image_id: str) -> str:
        path = self.image_dir / resume_id / f"{image_id}.png"
        self._write(path, content)
        return self._storage_key(path)

    def read_image(self, storage_key: str) -> bytes:
        return self._read(storage_key)

    def save_text(self, content: str, resume_id: str) -> str:
        path = self.text_dir / f"{resume_id}.txt"
        self._write(path, content.encode("utf-8"))
        return self._storage_key(path)

    def read_text(self, storage_key: str) -> str:
        try:
            return self._read(storage_key).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Invalid resume text encoding: {storage_key}") from exc

    def _write(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def _read(self, storage_key: str) -> bytes:
        path = self._resolve(storage_key)
        if not path.is_file():
            raise FileNotFoundError(storage_key)
        return path.read_bytes()

    def _resolve(self, storage_key: str) -> Path:
        root = self.root_path
        path = (root / storage_key).resolve()
        if path != root and root not in path.parents:
            raise ValueError(f"Invalid storage key: {storage_key}")
        return path

    def _storage_key(self, path: Path) -> str:
        return path.relative_to(self.root_path).as_posix()
