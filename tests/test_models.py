from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.controller.schema.schedule_dto import MeetingEntryCreateDTO
from app.model.enums import EntryStatus
from app.model.meeting_entry import MeetingEntry


def test_meeting_entry_normalizes_naive_datetime_and_status():
    entry = MeetingEntry(
        candidate_name="张三",
        subject="后端面试",
        start_time="2026-09-03T10:00:00",
        end_time="2026-09-03T10:30:00",
    )

    assert entry.start_time.tzinfo is not None
    assert entry.date == "2026-09-03"
    assert entry.status_at(datetime(2026, 9, 3, 9, 59, tzinfo=ZoneInfo("Asia/Shanghai"))) is EntryStatus.UPCOMING
    assert entry.status_at(datetime(2026, 9, 3, 10, 10, tzinfo=ZoneInfo("Asia/Shanghai"))) is EntryStatus.ONGOING
    assert entry.status_at(datetime(2026, 9, 3, 10, 31, tzinfo=ZoneInfo("Asia/Shanghai"))) is EntryStatus.FINISHED


def test_meeting_entry_rejects_invalid_time_range():
    with pytest.raises(ValidationError):
        MeetingEntry(
            candidate_name="张三",
            subject="后端面试",
            start_time="2026-09-03T10:30:00",
            end_time="2026-09-03T10:00:00",
        )


def test_create_dto_splits_chinese_and_english_commas():
    dto = MeetingEntryCreateDTO(
        raw_text="会议时间：2026/09/03 10:00-10:30",
        interviewer_names="李四，王五,赵六",
    )

    assert dto.interviewer_names == ["李四", "王五", "赵六"]
