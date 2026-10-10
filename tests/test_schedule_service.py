from app.controller.schema.schedule_dto import MeetingEntryCreateDTO
from app.mapper.memory_schedule_mapper import MemoryScheduleMapper
from app.service.schedule_service import ScheduleService


def _invitation(candidate_name: str | None = None) -> MeetingEntryCreateDTO:
    return MeetingEntryCreateDTO(
        raw_text="""
会议主题：后端开发面试
会议时间：2026/09/03 10:00-10:30 (GMT+08:00) 中国标准时间 - 北京
https://meeting.tencent.com/dm/demo-meeting
#腾讯会议：519-881-509
""",
        candidate_name=candidate_name,
    )


def test_create_from_invitation_deduplicates_same_meeting():
    schedule_mapper = MemoryScheduleMapper()
    service = ScheduleService(schedule_mapper=schedule_mapper)

    first = service.create_from_invitation(_invitation("\u5f20\u4e09"))
    second = service.create_from_invitation(_invitation("\u674e\u56db"))

    assert second.id == first.id
    assert len(schedule_mapper.list_all()) == 1


def _entry(raw_text: str, candidate_name: str | None = None, source: str = "manual") -> MeetingEntryCreateDTO:
    return MeetingEntryCreateDTO(raw_text=raw_text, candidate_name=candidate_name, source=source)


def test_list_overview_groups_finished_and_today_and_excludes_personal():
    from datetime import datetime, timedelta, timezone

    from app.service.meeting_parser_service import MeetingParserService

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    schedule_mapper = MemoryScheduleMapper()
    parser = MeetingParserService()

    # Finished: past date.
    schedule_mapper.save(parser.parse(_entry("面试时间：2026-09-10 10:00-10:30 (GMT+08:00)", "张三")))
    # Today, already finished (earlier today).
    schedule_mapper.save(parser.parse(_entry("面试时间：2026-09-16 08:00-08:30 (GMT+08:00)", "王五")))
    # Today, still upcoming (later today).
    schedule_mapper.save(parser.parse(_entry("面试时间：2026-09-16 15:00-15:30 (GMT+08:00)", "李四")))
    # Personal today, must be excluded.
    schedule_mapper.save(parser.parse(_entry("面试时间：2026-09-16 16:00-16:30 (GMT+08:00)", "我", "personal")))

    service = ScheduleService(schedule_mapper=schedule_mapper, meeting_parser=parser)
    result = service.list_overview(now)

    assert {entry.candidate_name for entry in result["finished"]} == {"张三", "王五"}
    assert [entry.candidate_name for entry in result["finished"]] == ["王五", "张三"]
    assert [entry.candidate_name for entry in result["today"]] == ["李四"]
