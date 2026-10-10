from datetime import datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import cv2
import fitz
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.controller.schema.schedule_dto import MeetingEntryCreateDTO
from app.core.dependencies import (
    get_my_interview_service,
    get_resume_parser_service,
    get_schedule_service,
)
from app.main import app
from app.mapper.memory_my_resume_mapper import MemoryMyResumeMapper
from app.mapper.memory_resume_mapper import MemoryResumeMapper
from app.mapper.memory_schedule_mapper import MemoryScheduleMapper
from app.model.meeting_entry import MeetingEntry
from app.service.my_interview_service import MyInterviewService
from app.service.resume_parser_service import ResumeParserService
from app.service.schedule_service import ScheduleService


@pytest.fixture
def client():
    test_service = ScheduleService(schedule_mapper=MemoryScheduleMapper())
    app.dependency_overrides[get_schedule_service] = lambda: test_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


SAMPLE_INVITATION = """
会议主题：后端开发实习生张三的面试
会议时间：2026/09/03 10:00-10:30 (GMT+08:00) 中国标准时间 - 北京
https://meeting.tencent.com/dm/demo-meeting
#腾讯会议：519-881-509
"""


def test_index_page_smoke(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "会议日程".encode() in response.content
    assert "我的日程".encode() in response.content
    assert "粘贴会议邀请" in client.get("/meetings/new").text


def test_schedule_page_smoke(client):
    response = client.get("/schedule", params={"date": "2026-09-03"})
    assert response.status_code == 200
    assert "会议时间表".encode() in response.content


def test_enterprise_invitation_review_can_change_type_and_time(client):
    raw = "会议主题：面试沟通\n会议时间：2026/09/29 10:00-11:00"
    preview = client.post("/meetings/interviews", data={"raw_text": raw, "action": "preview"})
    assert preview.status_code == 200
    assert "核对解析结果" in preview.text
    saved = client.post("/meetings/interviews", data={
        "raw_text": raw, "action": "save", "reviewed_subject": "业务讨论",
        "reviewed_kind": "meeting", "reviewed_start": "2026-09-29T10:30",
        "reviewed_end": "2026-09-29T11:30", "reviewed_platform": "腾讯会议",
    }, follow_redirects=False)
    assert saved.status_code == 303
    page = client.get("/meetings/schedule?date=2026-09-29")
    assert "业务讨论" in page.text
    assert "今天的面试（0）" in page.text


def test_enterprise_dated_api_excludes_legacy_personal_entries(client):
    service = app.dependency_overrides[get_schedule_service]()
    entry = service.meeting_parser.parse(MeetingEntryCreateDTO(raw_text=SAMPLE_INVITATION))
    entry.source = "personal"
    service.schedule_mapper.save(entry)
    response = client.get("/api/v1/interviews", params={"date": entry.date})
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_generic_meeting_is_not_rendered_as_interview(client):
    raw_text = """会议时间：2026/09/29 13:00-18:00
点击链接加入会议或直接入会：
https://work.weixin.qq.com/webapp/tm/3OvpLy21qp3zV7C81qTVoh
#会议号：522-685-596
"""
    created = client.post("/api/v1/interviews", json={"raw_text": raw_text})
    assert created.status_code == 201
    entry = created.json()["data"]
    assert entry["kind"] == "meeting"

    schedule = client.get("/schedule", params={"date": "2026-09-29"})
    assert "未命名会议" in schedule.text
    assert "1 场安排" in schedule.text
    assert "今天的面试（0）" in schedule.text

    detail = client.get(f"/interviews/{entry['id']}")
    assert detail.status_code == 200
    assert "会议详情" in detail.text
    assert "企业微信会议" in detail.text
    assert "522-685-596" in detail.text
    assert "候选人信息" not in detail.text
    assert "原始简历" not in detail.text
    assert "AI 面试辅助" not in detail.text


def test_interview_api_create_list_detail_and_delete(client):
    response = client.post(
        "/api/v1/interviews",
        json={"raw_text": SAMPLE_INVITATION, "candidate_name": "张三", "position": "后端"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 0
    entry = body["data"]
    assert entry["candidate_name"] == "张三"
    assert entry["platform"] == "腾讯会议"

    list_response = client.get("/api/v1/interviews", params={"date": "2026-09-03"})
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1

    detail_response = client.get(f"/api/v1/interviews/{entry['id']}")
    assert detail_response.status_code == 200

    page_response = client.get(f"/interviews/{entry['id']}")
    assert page_response.status_code == 200

    delete_response = client.delete(f"/api/v1/interviews/{entry['id']}")
    assert delete_response.status_code == 200
    assert client.get(f"/api/v1/interviews/{entry['id']}").status_code == 404


def test_create_interview_with_invalid_time_returns_422(client):
    response = client.post("/api/v1/interviews", json={"raw_text": "没有时间的邀请"})
    assert response.status_code == 422
    assert "未识别到会议时间" in response.json()["detail"]


def test_resume_api_smoke(client):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), "Name ZhangSan Phone 13800000000")
    pdf_bytes = doc.tobytes()
    doc.close()

    response = client.post(
        "/api/v1/resumes/parse",
        files={"resume": ("resume.pdf", BytesIO(pdf_bytes), "application/pdf")},
    )
    assert response.status_code == 200
    resume = response.json()["data"]
    assert resume["candidate_name"] == "ZhangSan"
    assert client.get(f"/resumes/{resume['id']}/pdf").status_code == 200

def test_schedule_page_renders_grid_position_vars(client):
    client.post("/api/v1/interviews", json={"raw_text": SAMPLE_INVITATION, "candidate_name": "张三"})
    page = client.get("/schedule", params={"date": "2026-09-03"})
    assert page.status_code == 200
    html = page.text
    assert "--hour-height: 156px" in html
    assert "--start-min: 600" in html
    assert "--duration: 30" in html
    assert "--column: 1" in html
    assert "--columns: 1" in html
    assert '<span class="event-title">张三</span>' in html
    assert "10:00 - 10:30" in html
    assert "519-881-509" in html


def test_resume_pdf_inline_and_download(client):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), "Name ZhangSan Phone 13800000000")
    pdf_bytes = doc.tobytes()
    doc.close()

    response = client.post(
        "/api/v1/resumes/parse",
        files={"resume": ("resume.pdf", BytesIO(pdf_bytes), "application/pdf")},
    )
    resume_id = response.json()["data"]["id"]

    inline = client.get(f"/resumes/{resume_id}/pdf")
    assert inline.status_code == 200
    assert "attachment" not in (inline.headers.get("content-disposition") or "")

    download = client.get(f"/resumes/{resume_id}/download")
    assert download.status_code == 200
    assert "attachment" in (download.headers.get("content-disposition") or "")


def test_detail_without_resume_shows_local_upload_dropzone(client):
    response = client.post(
        "/api/v1/interviews",
        json={"raw_text": SAMPLE_INVITATION, "candidate_name": "张三"},
    )
    entry_id = response.json()["data"]["id"]

    page = client.get(f"/interviews/{entry_id}")

    assert page.status_code == 200
    html = page.text
    assert 'data-resume-upload-form' in html
    assert 'data-upload-zone' in html
    assert "请先将简历 PDF 下载到本地" in html
    assert f"/interviews/{entry_id}/resume" in html
    assert "data-toggle-ai-assistant disabled" in html
    assert "data-ai-modal" not in html


def test_upload_resume_from_detail_and_show_candidate_photo(client, tmp_path):
    resume_service = ResumeParserService(storage_dir=tmp_path)
    app.dependency_overrides[get_resume_parser_service] = lambda: resume_service
    try:
        response = client.post(
            "/api/v1/interviews",
            json={"raw_text": SAMPLE_INVITATION, "candidate_name": "张三"},
        )
        entry_id = response.json()["data"]["id"]

        doc = fitz.open()
        page = doc.new_page()
        # 合成一张证件照：白底 + 居中的肤色色块，用于走通证件照选择流程
        photo = np.full((320, 240, 3), 255, dtype=np.uint8)  # BGR 白底
        photo[40:280, 60:180] = (130, 150, 200)  # BGR 肤色色块
        _, png_buffer = cv2.imencode(".png", photo)
        page.insert_image(fitz.Rect(360, 60, 480, 220), stream=png_buffer.tobytes())
        page.insert_text((72, 300), "Name ZhangSan Phone 13800000000")
        pdf_bytes = doc.tobytes()
        doc.close()

        upload = client.post(
            f"/interviews/{entry_id}/resume",
            files={"resume": ("resume.pdf", BytesIO(pdf_bytes), "application/pdf")},
            follow_redirects=False,
        )
        assert upload.status_code == 303

        detail = client.get(f"/interviews/{entry_id}")
        assert detail.status_code == 200
        assert 'class="candidate-photo"' in detail.text

        image_path = next(
            fragment.split('"')[0]
            for fragment in detail.text.split('src="')[1:]
            if fragment.startswith("/resumes/")
        )
        assert "/images/1-1" in image_path
        image_response = client.get(image_path)
        assert image_response.status_code == 200, image_response.text
        assert image_response.headers["content-type"] == "image/png"
    finally:
        app.dependency_overrides.pop(get_resume_parser_service, None)


def test_schedule_overview_tabs_and_filtered_lists(client):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    client.post(
        "/api/v1/interviews",
        json={
            "raw_text": "会议主题：过去面试\n会议时间：2020-01-01 10:00-10:30 (GMT+08:00)\nhttps://meeting.tencent.com/dm/past\n#腾讯会议：111-222-333",
            "candidate_name": "王过去",
        },
    )
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    placed_today = now.hour < 22
    if placed_today:
        start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        end = start + timedelta(minutes=30)
        client.post(
            "/api/v1/interviews",
            json={
                "raw_text": f"会议主题：今日面试\n会议时间：{start:%Y-%m-%d %H:%M}-{end:%H:%M} (GMT+08:00)\nhttps://meeting.tencent.com/dm/today\n#腾讯会议：444-555-666",
                "candidate_name": "李今日",
            },
        )

    client.post(
        "/api/v1/interviews",
        json={
            "raw_text": (
                "字节跳动诚邀你参加字节跳动校园招聘-后端开发实习生-生活服务岗位的面试，"
                "感谢你的耐心等待。\n\n【面试信息】\n面试形式：视频面试\n"
                "面试时间：2020-01-02 14:00(GMT+08:00) China Standard Time - Beijing\n"
                "面试链接：https://t.zijieimg.com/abc"
            ),
            "candidate_name": "链接君",
        },
    )

    normal = client.get("/schedule")
    assert normal.status_code == 200
    assert "已过期面试".encode() in normal.content
    assert "今天的面试".encode() in normal.content

    expired = client.get("/schedule", params={"overview": "expired"})
    assert expired.status_code == 200
    assert "王过去".encode() in expired.content
    assert "链接君".encode() in expired.content
    assert b"overview-meeting-link" in expired.content
    assert b"https://t.zijieimg.com/abc" in expired.content

    today = client.get("/schedule", params={"overview": "today"})
    assert today.status_code == 200
    if placed_today:
        assert "李今日".encode() in today.content
def test_my_interviews_plan_list_order_join_meeting_and_personal_excluded(client, tmp_path):
    my_schedule_mapper = MemoryScheduleMapper()
    resume_mapper = MemoryResumeMapper()
    my_interview_service = MyInterviewService(
        schedule_mapper=my_schedule_mapper,
        resume_mapper=resume_mapper,
        profile_mapper=MemoryMyResumeMapper(),
    )
    app.dependency_overrides[get_my_interview_service] = lambda: my_interview_service
    app.dependency_overrides[get_resume_parser_service] = lambda: ResumeParserService(
        resume_mapper=resume_mapper,
        storage_dir=tmp_path,
    )
    try:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 90), "Name MySelf Phone 13800000001")
        pdf_bytes = doc.tobytes()
        doc.close()

        upload = client.post(
            "/my/resume",
            files={"resume": ("me.pdf", BytesIO(pdf_bytes), "application/pdf")},
            follow_redirects=False,
        )
        assert upload.status_code == 303

        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        start = now.replace(hour=18, minute=0, second=0, microsecond=0)
        end = start + timedelta(minutes=30)
        created = client.post(
            "/interviews",
            data={
                "raw_text": (
                    f"会议主题：算法一面\n会议时间：{start:%Y-%m-%d %H:%M}-{end:%H:%M} (GMT+08:00)\n"
                    "https://t.zijieimg.com/abc123"
                ),
                "candidate_name": "我自己",
                "destination": "mine",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303

        response = client.get("/my-interviews")
        assert response.status_code == 200
        html = response.text
        # 计划列表：今日面试在前、已结束在后，且不再有“其他”分组
        assert html.index("今日面试") < html.index("已结束")
        assert 'plan-group-title other' not in html
        assert 'plan-group-title finished' in html
        # 会议链接域名识别为飞书
        assert "飞书会议" in html
        # 卡片带进入会议按钮，复用详情页的链接打开方式
        assert 'class="plan-join-meeting"' in html
        assert 'href="https://t.zijieimg.com/abc123" target="_blank"' in html
    finally:
        app.dependency_overrides.pop(get_my_interview_service, None)
        app.dependency_overrides.pop(get_resume_parser_service, None)

def test_schedule_date_options_exclude_personal_interviews():
    mapper = MemoryScheduleMapper()
    mapper.save(
        MeetingEntry(
            candidate_name="天正",
            subject="字节跳动校园招聘-后端开发实习生-生活服务岗位的面试",
            start_time=datetime(2026, 5, 26, 14, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            end_time=datetime(2026, 5, 26, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            source="personal",
        )
    )
    app.dependency_overrides[get_schedule_service] = lambda: ScheduleService(schedule_mapper=mapper)
    try:
        with TestClient(app) as client:
            response = client.get("/schedule")
            assert response.status_code == 200
            assert "05-26" not in response.text
            assert "生活服务" not in response.text
    finally:
        app.dependency_overrides.pop(get_schedule_service, None)


def test_detail_page_prefers_feishu_platform_from_meeting_url():
    mapper = MemoryScheduleMapper()
    entry = mapper.save(
        MeetingEntry(
            candidate_name="天正",
            subject="字节跳动校园招聘-后端开发实习生-生活服务岗位的面试",
            start_time=datetime(2026, 5, 26, 14, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            end_time=datetime(2026, 5, 26, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            platform="视频面试",
            meeting_url="https://t.zijieimg.com/0G7Zz46JQH8/",
        )
    )
    app.dependency_overrides[get_schedule_service] = lambda: ScheduleService(schedule_mapper=mapper)
    try:
        with TestClient(app) as client:
            response = client.get(f"/interviews/{entry.id}")
            assert response.status_code == 200
            assert "飞书会议" in response.text
    finally:
        app.dependency_overrides.pop(get_schedule_service, None)
