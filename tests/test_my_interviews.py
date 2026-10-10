from io import BytesIO

import cv2
import fitz
import numpy as np
from fastapi.testclient import TestClient

from app.core.dependencies import get_my_interview_service, get_schedule_service
from app.main import app
from app.mapper.memory_my_resume_mapper import MemoryMyResumeMapper
from app.mapper.memory_resume_mapper import MemoryResumeMapper
from app.mapper.memory_schedule_mapper import MemoryScheduleMapper
from app.service.my_interview_service import MyInterviewService
from app.service.resume_parser_service import ResumeParserService
from app.service.schedule_service import ScheduleService

SAMPLE_INVITATION = """
会议主题：我的 2026-09-03 面试
会议时间：2026/09/03 10:00-10:30 (GMT+08:00) 中国标准时间 - 北京
https://meeting.tencent.com/dm/demo-meeting
#腾讯会议：519-881-509
"""


def build_services(storage_dir):
    schedule_service = ScheduleService(schedule_mapper=MemoryScheduleMapper())
    resume_service = ResumeParserService(storage_dir=storage_dir)
    my_service = MyInterviewService(
        schedule_mapper=schedule_service.schedule_mapper,
        resume_mapper=MemoryResumeMapper(),
        profile_mapper=MemoryMyResumeMapper(),
    )
    return schedule_service, resume_service, my_service


def override_services(my_service):
    app.dependency_overrides[get_schedule_service] = lambda: ScheduleService(
        schedule_mapper=my_service.schedule_mapper
    )
    app.dependency_overrides[get_my_interview_service] = lambda: my_service


def test_my_interviews_page_requires_own_resume(tmp_path):
    _, _, my_service = build_services(tmp_path)
    override_services(my_service)
    try:
        with TestClient(app) as client:
            response = client.get("/my-interviews")
        assert response.status_code == 200
        assert "还没有我的简历" in response.text
        assert "data-resume-upload-form" in response.text
        assert response.text.count('<a class="date-tab ') == 3
        assert "已结束" in response.text
        assert "今日面试" in response.text
        assert response.text.index("今日面试") < response.text.index("已结束")
        assert 'plan-group-title other' not in response.text
    finally:
        app.dependency_overrides.clear()


def test_personal_interview_added_and_excluded_from_normal_schedule(tmp_path):
    schedule_service, resume_service, my_service = build_services(tmp_path)
    override_services(my_service)
    try:
        with TestClient(app) as client:
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 90), "Name ZhangSan")
            pdf = doc.tobytes()
            doc.close()

            response = client.post(
                "/interviews",
                data={
                    "raw_text": SAMPLE_INVITATION,
                    "destination": "mine",
                },
                files={"resume": ("resume.pdf", BytesIO(pdf), "application/pdf")},
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers["location"].startswith("/my-interviews?date=")

            my_page = client.get("/my-interviews", params={"date": "2026-09-03"})
            assert my_page.status_code == 200
            assert "ZhangSan" in my_page.text or "我的 2026-09-03 面试" in my_page.text
            assert "我的 2026-09-03 面试" in my_page.text

            normal_page = client.get("/schedule", params={"date": "2026-09-03"})
            assert normal_page.status_code == 200
            assert "我的 2026-09-03 面试" not in normal_page.text

            api = client.get("/api/v1/interviews")
            assert api.status_code == 200
            assert all(item["candidate_name"] != "我的 2026-09-03 面试" for item in api.json()["data"])
    finally:
        app.dependency_overrides.clear()


def test_personal_interview_requires_resume(tmp_path):
    schedule_service, _, my_service = build_services(tmp_path)
    override_services(my_service)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/interviews",
                data={"raw_text": SAMPLE_INVITATION, "destination": "mine"},
                follow_redirects=False,
            )
        assert response.status_code == 422
        assert "请先上传我的简历" in response.text
    finally:
        app.dependency_overrides.clear()