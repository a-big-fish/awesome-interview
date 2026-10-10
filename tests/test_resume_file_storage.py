from pathlib import Path

import pytest

from app.mapper.local_resume_file_storage import LocalResumeFileStorage


def test_local_resume_file_storage_saves_and_reads_files(tmp_path):
    storage = LocalResumeFileStorage(tmp_path)

    pdf_key = storage.save_pdf(b"pdf-bytes", "张三 简历.pdf", "resume-1")
    image_key = storage.save_image(b"png-bytes", "resume-1", "1-1")

    assert pdf_key.startswith("resumes/resume-1")
    assert pdf_key.endswith(".pdf")
    assert image_key == "resume_images/resume-1/1-1.png"
    assert storage.read_pdf(pdf_key) == b"pdf-bytes"
    assert storage.read_image(image_key) == b"png-bytes"
    assert (tmp_path / image_key).is_file()

    text_key = storage.save_text("Name ZhangSan", "resume-1")
    assert text_key == "resume_info/resume-1.txt"
    assert storage.read_text(text_key) == "Name ZhangSan"


def test_local_resume_file_storage_rejects_missing_file(tmp_path):
    storage = LocalResumeFileStorage(tmp_path)

    with pytest.raises(FileNotFoundError):
        storage.read_pdf("resumes/missing.pdf")
