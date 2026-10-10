from fastapi.testclient import TestClient

from app.core.dependencies import get_schedule_service
from app.main import app
from app.mapper.memory_enterprise_calendar_mapper import MemoryEnterpriseCalendarMapper
from app.mapper.memory_schedule_mapper import MemoryScheduleMapper
from app.service.enterprise_calendar_service import EnterpriseCalendarService
from app.service.schedule_service import ScheduleService


LUNCH_INVITATION = "会议主题：午间讨论\n会议时间：2026/10/02 12:15-12:45\n"


def test_api_requires_confirmation_for_enterprise_rest_overlap():
    service = ScheduleService(
        schedule_mapper=MemoryScheduleMapper(),
        calendar_service=EnterpriseCalendarService(MemoryEnterpriseCalendarMapper()),
    )
    app.dependency_overrides[get_schedule_service] = lambda: service
    try:
        with TestClient(app) as client:
            warning = client.post("/api/v1/interviews", json={"raw_text": LUNCH_INVITATION})
            assert warning.status_code == 409
            assert "午休" in str(warning.json()["detail"]["warnings"])
            assert service.list_all() == []
            accepted = client.post(
                "/api/v1/interviews?confirm_non_working=true",
                json={"raw_text": LUNCH_INVITATION},
            )
            assert accepted.status_code == 201
            assert len(service.list_all()) == 1
    finally:
        app.dependency_overrides.pop(get_schedule_service, None)


def test_page_shows_soft_warning_before_adding_meeting():
    service = ScheduleService(
        schedule_mapper=MemoryScheduleMapper(),
        calendar_service=EnterpriseCalendarService(MemoryEnterpriseCalendarMapper()),
    )
    app.dependency_overrides[get_schedule_service] = lambda: service
    try:
        with TestClient(app) as client:
            warning = client.post(
                "/interviews", data={"raw_text": LUNCH_INVITATION, "destination": "schedule"}
            )
            assert warning.status_code == 409
            assert "仍添加到时间表" in warning.text
            assert service.list_all() == []
            import re

            token = re.search(r'name="confirmation_token" value="([a-f0-9]+)"', warning.text)
            assert token
            accepted = client.post(
                "/interviews",
                data={
                    "raw_text": LUNCH_INVITATION,
                    "destination": "schedule",
                    "confirmation_token": token.group(1),
                },
                follow_redirects=False,
            )
            assert accepted.status_code == 303
            assert len(service.list_all()) == 1
    finally:
        app.dependency_overrides.pop(get_schedule_service, None)
