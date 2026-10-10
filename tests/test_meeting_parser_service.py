from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.controller.schema.schedule_dto import MeetingEntryCreateDTO
from app.core.exceptions import MeetingParseError
from app.model.meeting_entry import MeetingEntry
from app.service.meeting_parser_service import MeetingParserService


def test_parse_tencent_meeting_invitation():
    raw_text = """张三 邀请您参加腾讯会议
会议主题：后端开发实习生张三的面试
会议时间：2026/09/03 10:00-10:30 (GMT+08:00) 中国标准时间 - 北京
点击链接入会：https://meeting.tencent.com/dm/demo-meeting
#腾讯会议：519-881-509
"""
    dto = MeetingEntryCreateDTO(raw_text=raw_text, candidate_name="张三")
    entry = MeetingParserService().parse(dto)

    assert entry.subject == "后端开发实习生张三的面试"
    assert entry.candidate_name == "张三"
    assert entry.start_time.isoformat() == "2026-09-03T10:00:00+08:00"
    assert entry.end_time.isoformat() == "2026-09-03T10:30:00+08:00"
    assert entry.platform == "腾讯会议"
    assert entry.room_number == "519-881-509"
    assert str(entry.meeting_url) == "https://meeting.tencent.com/dm/demo-meeting"


def test_parse_missing_time_raises_clear_error():
    dto = MeetingEntryCreateDTO(raw_text="会议主题：张三的面试")
    with pytest.raises(MeetingParseError, match="未识别到会议时间"):
        MeetingParserService().parse(dto)

def test_parse_candidate_name_strips_company_and_role_prefix():
    raw_text = """
会议主题：帝欧水华实习生符传朔的面试
会议时间：2026/09/03 10:00-10:30 (GMT+08:00) 中国标准时间 - 北京
https://meeting.tencent.com/dm/demo-meeting
#腾讯会议：519-881-509
"""
    dto = MeetingEntryCreateDTO(raw_text=raw_text)
    entry = MeetingParserService().parse(dto)
    assert entry.candidate_name == "符传朔"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("帝欧水华实习生符传朔", "符传朔"),
        ("后端开发实习生张三", "张三"),
        ("张三实习生", "张三"),
        ("后端开发张三", "张三"),
        ("张三", "张三"),
    ],
)
def test_clean_candidate_name(raw, expected):
    assert MeetingParserService()._clean_candidate_name(raw) == expected


def test_parse_candidate_name_falls_back_to_subject():
    raw_text = """
会议主题：后端开发面试
会议时间：2026/09/03 10:00-10:30 (GMT+08:00) 中国标准时间 - 北京
https://meeting.tencent.com/dm/demo-meeting
#腾讯会议：519-881-509
"""
    dto = MeetingEntryCreateDTO(raw_text=raw_text)
    entry = MeetingParserService().parse(dto)

    assert entry.candidate_name == "后端开发面试"
    assert entry.subject == "后端开发面试"


def test_parse_bytedance_invitation_template():
    raw_text = """天正：

字节跳动诚邀你参加字节跳动校园招聘-后端开发实习生-生活服务岗位的面试，感谢你的耐心等待。

【面试信息】
面试形式：视频面试
面试时间：2026-05-26 14:00(GMT+08:00) China Standard Time - Beijing
面试链接：[https://t.zijieimg.com/0G7Zz46JQH8/](https://t.zijieimg.com/0G7Zz46JQH8/)
视频面试开始前，请下载飞书最新版本，下载链接：[https://www.feishu.cn/download](https://www.feishu.cn/download)
"""
    dto = MeetingEntryCreateDTO(raw_text=raw_text)
    entry = MeetingParserService().parse(dto)

    assert entry.candidate_name == "天正"
    assert entry.position == "字节跳动校园招聘-后端开发实习生-生活服务"
    assert entry.subject == "字节跳动校园招聘-后端开发实习生-生活服务岗位的面试"
    assert entry.start_time.isoformat() == "2026-05-26T14:00:00+08:00"
    assert entry.end_time.isoformat() == "2026-05-26T15:00:00+08:00"
    assert entry.platform == "飞书会议"
    assert entry.room_number is None
    assert str(entry.meeting_url) == "https://t.zijieimg.com/0G7Zz46JQH8/"


def test_parse_bytedance_falls_back_to_interview_format_without_known_url():
    raw_text = "字节跳动诚邀你参加后端开发实习生岗位的面试\n面试时间：2026-05-26 14:00(GMT+08:00)\n面试形式：视频面试\n面试链接：https://example.com/invite/1"
    dto = MeetingEntryCreateDTO(raw_text=raw_text, candidate_name="陈晨")
    entry = MeetingParserService().parse(dto)
    assert entry.platform == "视频面试"
    assert str(entry.meeting_url) == "https://example.com/invite/1"


def test_parse_bytedance_uses_provided_candidate_name():
    raw_text = "字节跳动诚邀你参加字节跳动校园招聘-后端开发实习生岗位的面试\n面试时间：2026-05-26 14:00(GMT+08:00)\n面试链接：https://t.zijieimg.com/0G7Zz46JQH8/"
    dto = MeetingEntryCreateDTO(raw_text=raw_text, candidate_name="王小明")
    entry = MeetingParserService().parse(dto)
    assert entry.candidate_name == "王小明"


def test_parse_single_time_only_infers_end():
    raw_text = "某公司面试\n时间：2026/06/01 10:00 (GMT+08:00)\nhttps://meeting.tencent.com/dm/x"
    dto = MeetingEntryCreateDTO(raw_text=raw_text, candidate_name="李四")
    entry = MeetingParserService().parse(dto)
    assert entry.start_time.isoformat() == "2026-06-01T10:00:00+08:00"
    assert entry.end_time.isoformat() == "2026-06-01T11:00:00+08:00"

def test_display_platform_prefers_known_url_domain():
    entry = MeetingEntry(
        candidate_name="天正",
        subject="岗位面试",
        start_time=datetime(2026, 5, 26, 14, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        end_time=datetime(2026, 5, 26, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        platform="视频面试",
        meeting_url="https://t.zijieimg.com/0G7Zz46JQH8/",
    )
    assert MeetingParserService.display_platform(entry) == "飞书会议"


def test_display_platform_falls_back_to_stored_platform():
    entry = MeetingEntry(
        candidate_name="陈晨",
        subject="岗位面试",
        start_time=datetime(2026, 5, 26, 14, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        end_time=datetime(2026, 5, 26, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        platform="视频面试",
        meeting_url="https://example.com/invite/1",
    )
    assert MeetingParserService.display_platform(entry) == "视频面试"


def test_parse_untitled_wecom_meeting():
    raw_text = """会议时间：2026/09/29 13:00-18:00
点击链接加入会议或直接入会：
https://work.weixin.qq.com/webapp/tm/3OvpLy21qp3zV7C81qTVoh
#会议号：522-685-596
"""
    entry = MeetingParserService().parse(MeetingEntryCreateDTO(raw_text=raw_text))

    assert entry.kind == "meeting"
    assert entry.subject == "未命名会议"
    assert entry.start_time.isoformat() == "2026-09-29T13:00:00+08:00"
    assert entry.end_time.isoformat() == "2026-09-29T18:00:00+08:00"
    assert entry.platform == "企业微信会议"
    assert entry.room_number == "522-685-596"
    assert str(entry.meeting_url) == "https://work.weixin.qq.com/webapp/tm/3OvpLy21qp3zV7C81qTVoh"
