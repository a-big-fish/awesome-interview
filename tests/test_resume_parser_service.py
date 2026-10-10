from pathlib import Path

import cv2
import fitz
import numpy as np
import pytest

from app.core.exceptions import ResumeParseError
from app.mapper.local_resume_file_storage import LocalResumeFileStorage
from app.service.resume_parser_service import ResumeParserService


def create_sample_pdf(path: Path) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 90), "Name ZhangSan")
    page.insert_text((72, 120), "Phone 13800000000")
    page.insert_text((72, 150), "Email zhangsan@example.com")
    content = doc.tobytes()
    doc.close()
    path.write_bytes(content)
    return content


def test_parse_pdf_extracts_text_and_basic_fields(tmp_path):
    service = ResumeParserService(storage_dir=tmp_path)
    content = create_sample_pdf(tmp_path / "resume.pdf")

    resume = service.parse_pdf(content, "resume.pdf")

    assert resume.file_name == "resume.pdf"
    assert resume.page_count == 1
    assert "ZhangSan" in resume.raw_text
    assert resume.candidate_name == "ZhangSan"
    assert resume.phone == "13800000000"
    assert resume.email == "zhangsan@example.com"
    assert service.read_pdf(resume.id) == content
    assert resume.text_path == f"resume_info/{resume.id}.txt"
    assert service.read_text(resume.id).startswith("Name ZhangSan")


def test_parse_pdf_rejects_invalid_file(tmp_path):
    service = ResumeParserService(storage_dir=tmp_path)
    with pytest.raises(ResumeParseError):
        service.parse_pdf(b"not a pdf", "resume.pdf")

def build_photo_pdf(path: Path, with_photo: bool) -> bytes:
    """生成简历 PDF；with_photo=True 时嵌入一张合成的证件照（白底 + 肤色色块）。"""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    if with_photo:
        photo = np.full((320, 240, 3), 255, dtype=np.uint8)  # BGR 白底
        photo[40:280, 60:180] = (130, 150, 200)  # BGR 肤色色块
        _, png_buffer = cv2.imencode(".png", photo)
        page.insert_image(fitz.Rect(360, 60, 480, 220), stream=png_buffer.tobytes())
    page.insert_text((72, 300), "Name ZhangSan Phone 13800000000")
    content = doc.tobytes()
    doc.close()
    path.write_bytes(content)
    return content


def test_parse_pdf_detects_and_marks_candidate_photo(tmp_path):
    service = ResumeParserService(storage_dir=tmp_path)
    content = build_photo_pdf(tmp_path / "resume.pdf", with_photo=True)

    resume = service.parse_pdf(content, "resume.pdf")

    assert len(resume.images) == 1
    assert resume.images[0].image_id == "1-1"
    assert resume.candidate_photo_id == "1-1"


def test_parse_pdf_without_photo_leaves_candidate_photo_id_none(tmp_path):
    service = ResumeParserService(storage_dir=tmp_path)
    content = build_photo_pdf(tmp_path / "resume.pdf", with_photo=False)

    resume = service.parse_pdf(content, "resume.pdf")

    assert resume.images == []
    assert resume.candidate_photo_id is None
