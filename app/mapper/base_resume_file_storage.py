from abc import ABC, abstractmethod


class ResumeFileStorage(ABC):
    """Storage boundary for resume files and parsed resume artifacts."""

    @abstractmethod
    def save_pdf(self, content: bytes, file_name: str, resume_id: str) -> str:
        """Store a resume PDF and return its storage key."""
        raise NotImplementedError

    @abstractmethod
    def read_pdf(self, storage_key: str) -> bytes:
        """Read a stored resume PDF."""
        raise NotImplementedError

    @abstractmethod
    def save_image(self, content: bytes, resume_id: str, image_id: str) -> str:
        """Store an extracted resume image and return its storage key."""
        raise NotImplementedError

    @abstractmethod
    def read_image(self, storage_key: str) -> bytes:
        """Read a stored resume image."""
        raise NotImplementedError

    @abstractmethod
    def save_text(self, content: str, resume_id: str) -> str:
        """Store parsed resume text and return its storage key."""
        raise NotImplementedError

    @abstractmethod
    def read_text(self, storage_key: str) -> str:
        """Read parsed resume text."""
        raise NotImplementedError
