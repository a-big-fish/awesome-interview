from datetime import date, time

import pytest
from pydantic import ValidationError

from app.mapper.memory_enterprise_calendar_mapper import MemoryEnterpriseCalendarMapper
from app.model.enterprise_calendar import EnterpriseCalendarSettings, RestPeriod, WorkdaySchedule
from app.service.enterprise_calendar_service import EnterpriseCalendarService


def test_defaults_match_existing_visible_hours_and_breaks():
    settings = EnterpriseCalendarSettings()
    day = settings.for_date(date(2026, 10, 2))
    assert (day.start, day.end) == (time(9), time(19))
    assert [(item.name, item.start, item.end) for item in day.breaks] == [
        ("午休", time(12), time(13)),
        ("茶歇", time(16), time(16, 30)),
    ]


def test_rejects_overlapping_and_outside_breaks():
    with pytest.raises(ValidationError, match="不能重叠"):
        WorkdaySchedule(breaks=[
            RestPeriod(name="午休", start=time(12), end=time(13)),
            RestPeriod(name="培训休息", start=time(12, 30), end=time(13, 30)),
        ])
    with pytest.raises(ValidationError, match="工作时间内"):
        WorkdaySchedule(breaks=[RestPeriod(name="早休", start=time(8), end=time(8, 30))])


def test_settings_roundtrip_and_memory_mapper_isolation():
    mapper = MemoryEnterpriseCalendarMapper()
    settings = EnterpriseCalendarSettings()
    settings.days[0].breaks = [RestPeriod(name="短休", start=time(10), end=time(10, 15))]
    mapper.save(settings)
    settings.days[0].breaks.clear()
    loaded = mapper.get()
    assert loaded is not None
    assert loaded.days[0].breaks[0].name == "短休"
    assert EnterpriseCalendarSettings.model_validate_json(loaded.model_dump_json()).days[0].breaks[0].name == "短休"


def test_shaded_blocks_are_clipped_and_warnings_do_not_block_meetings():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    service = EnterpriseCalendarService(MemoryEnterpriseCalendarMapper())
    blocks = service.shaded_blocks(date(2026, 10, 2), 11 * 60, 17 * 60)
    assert [(item["label"], item["start_minutes"], item["duration_minutes"]) for item in blocks] == [
        ("午休", 720, 60),
        ("茶歇", 960, 30),
    ]
    zone = ZoneInfo("Asia/Shanghai")
    warnings = service.overlap_warnings(
        datetime(2026, 10, 2, 12, 30, tzinfo=zone),
        datetime(2026, 10, 2, 13, 30, tzinfo=zone),
    )
    assert len(warnings) == 1
    assert "午休" in warnings[0]
