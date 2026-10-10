import logging
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np
import pymupdf as fitz
from fastapi import UploadFile

from app.core.exceptions import ResumeFileNotFoundError, ResumeParseError
from app.mapper.base_resume_file_storage import ResumeFileStorage
from app.mapper.base_resume_mapper import BaseResumeMapper
from app.mapper.local_resume_file_storage import LocalResumeFileStorage
from app.mapper.memory_resume_mapper import MemoryResumeMapper
from app.model.resume import Resume, ResumeImage
from app.service.candidate_photo_selector import (
    CandidatePhotoSelector,
    PhotoCandidate,
    pixmap_to_bgr,
)

logger = logging.getLogger(__name__)
MAX_RESUME_BYTES = 20 * 1024 * 1024


class _AppendFileHandler(logging.Handler):
    """每次写日志时打开文件并追加，避免长期占用文件句柄（便于 Windows 下清理临时目录）。"""

    def __init__(self, file_path: Path) -> None:
        super().__init__()
        self.file_path = file_path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            with self.file_path.open("a", encoding="utf-8") as file_handle:
                file_handle.write(message + "\n")
        except Exception:  # noqa: BLE001
            self.handleError(record)


def _configure_photo_logging(log_dir: Path) -> None:
    """控制台只输出「每份简历是否解析出照片」的摘要，详细过程与报错写入日志文件。"""
    if logger.handlers:
        return
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = _AppendFileHandler(log_dir / "resume_parser.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


class ParseStepTimer:
    """Collect elapsed time for each resume parsing phase."""

    def __init__(self) -> None:
        self.durations: dict[str, float] = {}

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            self.durations[name] = self.durations.get(name, 0.0) + (
                perf_counter() - started
            )

    def summary(self, overall_started: float) -> str:
        values = self.durations.copy()
        values["total"] = perf_counter() - overall_started
        return " | ".join(
            f"{name}={seconds * 1000:.1f}ms"
            for name, seconds in values.items()
        )


class ResumeParserService:
    """Extract text, basic fields and images from a resume PDF."""

    def __init__(
        self,
        resume_mapper: BaseResumeMapper | None = None,
        storage_dir: Path | str = Path("data"),
        min_image_size: int = 80,
        photo_selector: CandidatePhotoSelector | None = None,
        file_storage: ResumeFileStorage | None = None,
    ) -> None:
        self.resume_mapper = resume_mapper or MemoryResumeMapper()
        self.storage_dir = Path(storage_dir)
        self.file_storage = file_storage or LocalResumeFileStorage(self.storage_dir)
        self.min_image_size = min_image_size
        self.photo_selector = photo_selector or CandidatePhotoSelector()
        _configure_photo_logging(self.storage_dir / "logs")

    async def parse_upload(self, upload: UploadFile, owner_id: str = "local") -> Resume:
        timer = ParseStepTimer()
        overall_started = perf_counter()
        if upload.filename and not upload.filename.lower().endswith(".pdf"):
            raise ResumeParseError("仅支持 PDF 简历文件")
        with timer.step("read_upload"):
            content = await upload.read(MAX_RESUME_BYTES + 1)
        if not content:
            raise ResumeParseError("简历文件为空")
        if len(content) > MAX_RESUME_BYTES:
            raise ResumeParseError("简历文件不得超过 20 MB")
        resume = self.parse_pdf(
            content,
            upload.filename or "resume.pdf",
            timer=timer,
            overall_started=overall_started,
            owner_id=owner_id,
        )
        logger.info(
            "简历上传完成，总耗时 %.3fs",
            perf_counter() - overall_started,
        )
        return resume

    def parse_pdf(
        self,
        content: bytes,
        file_name: str,
        timer: ParseStepTimer | None = None,
        overall_started: float | None = None,
        owner_id: str = "local",
    ) -> Resume:
        timer = timer or ParseStepTimer()
        overall_started = (
            overall_started if overall_started is not None else perf_counter()
        )
        resume_id = str(uuid4())
        with timer.step("save_pdf"):
            pdf_key = self.file_storage.save_pdf(content, file_name, resume_id)
        try:
            with timer.step("open_pdf"):
                doc = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            logger.debug("无法读取 PDF：%s", type(exc).__name__)
            raise ResumeParseError("无法读取 PDF 文件，请确认文件未被损坏") from exc

        text_parts: list[str] = []
        images: list[ResumeImage] = []
        photo_candidates: list[PhotoCandidate] = []
        seen_xrefs: set[int] = set()
        try:
            for page_number, page in enumerate(doc, start=1):
                with timer.step("extract_text"):
                    text_parts.append(page.get_text())
                for image_index, image_info in enumerate(page.get_images(full=True), start=1):
                    xref = image_info[0]
                    if xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)
                    with timer.step("extract_images"):
                        image, bgr = self._extract_image(
                            doc, xref, resume_id, page_number, image_index
                        )
                    if image:
                        images.append(image)
                        if bgr is not None:
                            photo_candidates.append(
                                PhotoCandidate(
                                    image_id=image.image_id,
                                    bgr=bgr,
                                    page_number=page_number,
                                    width=image.width or 0,
                                    height=image.height or 0,
                                )
                            )
            page_count = doc.page_count
        finally:
            doc.close()

        raw_text = "\n".join(part.strip() for part in text_parts if part and part.strip())
        with timer.step("save_text"):
            text_key = self.file_storage.save_text(raw_text, resume_id)
        with timer.step("select_photo"):
            selection = self.photo_selector.select_one(photo_candidates)
        candidate_photo_id = selection.selected.image_id if selection.selected else None

        with timer.step("save_metadata"):
            resume = Resume(
                id=resume_id,
                owner_id=owner_id,
                file_name=file_name,
                pdf_path=pdf_key,
                text_path=text_key,
                page_count=page_count,
                candidate_name=self._extract_candidate_name(raw_text),
                email=self._extract_email(raw_text),
                phone=self._extract_phone(raw_text),
                raw_text=raw_text,
                images=images,
                candidate_photo_id=candidate_photo_id,
            )
            saved_resume = self.resume_mapper.save(resume)

        logger.info(
            "简历解析完成 [%s] 照片: %s, 页数: %d, 图片: %d, %s",
            file_name,
            "有" if candidate_photo_id else "无",
            page_count,
            len(images),
            timer.summary(overall_started),
        )
        logger.debug(
            "照片选择: strategy=%s, 提取图片=%d, 尺寸候选=%d, 通过候选=%d, 选中=%s, 落盘=%s",
            selection.strategy,
            len(photo_candidates),
            len(photo_candidates),
            len(selection.candidates),
            candidate_photo_id,
            pdf_key,
        )
        return saved_resume

    def _extract_image(
        self,
        doc: fitz.Document,
        xref: int,
        resume_id: str,
        page_number: int,
        image_index: int,
    ) -> tuple[ResumeImage | None, np.ndarray | None]:
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.width < self.min_image_size or pix.height < self.min_image_size:
                logger.debug(
                    "跳过小图 page_%s-image_%s (%dx%d)",
                    page_number,
                    image_index,
                    pix.width,
                    pix.height,
                )
                return None, None
            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            bgr = pixmap_to_bgr(pix)
            png_bytes = pix.tobytes("png")
            storage_key = self.file_storage.save_image(
                png_bytes, resume_id, f"{page_number}-{image_index}"
            )
            image = ResumeImage(
                image_id=f"{page_number}-{image_index}",
                page_number=page_number,
                file_path=storage_key,
                width=pix.width,
                height=pix.height,
            )
            logger.debug(
                "提取图片 page_%s-image_%s: %dx%d, 落盘=%s",
                page_number,
                image_index,
                pix.width,
                pix.height,
                storage_key,
            )
            return image, bgr
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "提取图片失败 page_%s-image_%s: %s", page_number, image_index, exc
            )
            return None, None

    def _extract_candidate_name(self, text: str) -> str | None:
        patterns = (
            r"姓名\s*[：:]?\s*([^\s，,。;]{2,20})",
            r"Name\s*[：:]?\s*([^\s，,。;]{2,50})",
            r"([\u4e00-\u9fa5]{2,4})\s*的简历",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_email(self, text: str) -> str | None:
        match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        return match.group(0) if match else None

    def _extract_phone(self, text: str) -> str | None:
        match = re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", text)
        return match.group(0) if match else None

    def get_resume(self, resume_id: str) -> Resume | None:
        return self.resume_mapper.find_by_id(resume_id)

    def read_pdf(self, resume_id: str) -> bytes:
        """Read the stored PDF for a resume through the storage boundary."""
        resume = self.get_resume(resume_id)
        if not resume:
            raise ResumeFileNotFoundError(resume_id)
        try:
            return self.file_storage.read_pdf(resume.pdf_path)
        except FileNotFoundError as exc:
            raise ResumeFileNotFoundError(resume.pdf_path) from exc

    def read_image(self, resume_id: str, image_id: str) -> bytes:
        """Read a stored image belonging to a resume."""
        resume = self.get_resume(resume_id)
        image = (
            next((item for item in resume.images if item.image_id == image_id), None)
            if resume
            else None
        )
        if not image:
            raise ResumeFileNotFoundError(image_id)
        try:
            return self.file_storage.read_image(image.file_path)
        except FileNotFoundError as exc:
            raise ResumeFileNotFoundError(image.file_path) from exc

    def read_text(self, resume_id: str) -> str:
        """Read persisted parsed text belonging to a resume."""
        resume = self.get_resume(resume_id)
        if not resume:
            raise ResumeFileNotFoundError(resume_id)
        if not resume.text_path:
            raise ResumeFileNotFoundError(resume_id)
        try:
            return self.file_storage.read_text(resume.text_path)
        except FileNotFoundError as exc:
            raise ResumeFileNotFoundError(resume.text_path) from exc
