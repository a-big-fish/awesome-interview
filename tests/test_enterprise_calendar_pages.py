from fastapi.testclient import TestClient

from app.core.dependencies import get_enterprise_calendar_service
from app.main import app
from app.mapper.memory_enterprise_calendar_mapper import MemoryEnterpriseCalendarMapper
from app.service.enterprise_calendar_service import EnterpriseCalendarService


def _settings_form() -> dict[str, str | list[str]]:
    data: dict[str, str | list[str]] = {"timezone": "Asia/Shanghai"}
    for weekday in range(7):
        data[f"enabled_{weekday}"] = "on"
        data[f"start_{weekday}"] = "08:30"
        data[f"end_{weekday}"] = "18:00"
        data[f"break_name_{weekday}"] = "午休"
        data[f"break_start_{weekday}"] = "11:30"
        data[f"break_end_{weekday}"] = "12:30"
    return data


def test_enterprise_settings_persist_and_render_shading():
    service = EnterpriseCalendarService(MemoryEnterpriseCalendarMapper())
    app.dependency_overrides[get_enterprise_calendar_service] = lambda: service
    try:
        with TestClient(app) as client:
            saved = client.post("/meetings/settings", data=_settings_form(), follow_redirects=False)
            assert saved.status_code == 303
            page = client.get("/meetings/settings")
            assert page.status_code == 200
            assert 'value="08:30"' in page.text
            schedule = client.get("/schedule", params={"date": "2026-10-02", "start_time": "08:00", "end_time": "19:00"})
            assert schedule.status_code == 200
            assert "午休" in schedule.text
            assert "--block-start: 690" in schedule.text
            assert "下班后" in schedule.text
            assert 'data-now-grid' in schedule.text
            assert 'data-time-zone="Asia/Shanghai"' in schedule.text
    finally:
        app.dependency_overrides.pop(get_enterprise_calendar_service, None)


def test_enterprise_settings_reject_invalid_break_overlap():
    service = EnterpriseCalendarService(MemoryEnterpriseCalendarMapper())
    app.dependency_overrides[get_enterprise_calendar_service] = lambda: service
    data = _settings_form()
    data["break_name_0"] = ["午休", "第二段"]
    data["break_start_0"] = ["11:30", "12:00"]
    data["break_end_0"] = ["12:30", "13:00"]
    try:
        with TestClient(app) as client:
            response = client.post("/meetings/settings", data=data)
            assert response.status_code == 422
            assert "不能重叠" in response.text
    finally:
        app.dependency_overrides.pop(get_enterprise_calendar_service, None)


def test_disabled_break_is_saved_without_shading():
    service = EnterpriseCalendarService(MemoryEnterpriseCalendarMapper())
    app.dependency_overrides[get_enterprise_calendar_service] = lambda: service
    data = _settings_form()
    for weekday in range(7):
        data[f"break_enabled_{weekday}"] = "off"
    try:
        with TestClient(app) as client:
            assert client.post("/meetings/settings", data=data, follow_redirects=False).status_code == 303
            assert 'value="off" selected' in client.get("/meetings/settings").text
            schedule = client.get("/meetings/schedule?date=2026-10-02")
            assert "午休" not in schedule.text
    finally:
        app.dependency_overrides.pop(get_enterprise_calendar_service, None)
