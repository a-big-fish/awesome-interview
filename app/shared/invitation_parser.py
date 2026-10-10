import re
from datetime import datetime, timedelta, timezone

from app.core.exceptions import MeetingParseError
from pydantic import BaseModel


class InvitationFacts(BaseModel):
    """Business-neutral facts extracted from one invitation."""

    subject: str | None
    kind_hint: str
    candidate_name_hint: str | None = None
    position_hint: str | None = None
    start_time: datetime
    end_time: datetime
    platform: str
    room_number: str | None = None
    meeting_url: str | None = None


class InvitationParser:
    """Extract meeting facts shared by the enterprise and personal apps."""

    PLATFORM_RULES = [
        ("meeting.tencent.com", "腾讯会议"),
        ("meeting.tencent", "腾讯会议"),
        ("zoom.us", "Zoom"),
        ("feishu.cn", "飞书会议"),
        ("larksuite.com", "飞书会议"),
        ("t.zijieimg.com", "飞书会议"),
        ("work.weixin.qq.com", "企业微信会议"),
        ("teams.microsoft.com", "Microsoft Teams"),
        ("meeting.alibaba.com", "钉钉会议"),
        ("go.to", "GoTo Meeting"),
    ]

    URL_LABELS = ("面试链接", "面试地址", "会议链接", "会议地址", "入会链接", "入会网址")

    # Some invitations (e.g. ByteDance) only provide a start time; infer a
    # default duration so the schedule can still place the interview.
    SINGLE_TIME_INFERRED_DURATION = timedelta(minutes=60)

    _RANGE_TIME_PATTERN = re.compile(
        r"(?:会议时间|面试时间|时间|Time|Date)\s*[:：]?\s*"
        r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?\s*"
        r"(\d{1,2})\s*[:：]\s*(\d{2})\s*(?:-|—|~|至|到)\s*"
        r"(\d{1,2})\s*[:：]\s*(\d{2})",
        re.IGNORECASE,
    )

    _SINGLE_TIME_PATTERN = re.compile(
        r"(?:会议时间|面试时间|时间|Time|Date)\s*[:：]?\s*"
        r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?\s*"
        r"(\d{1,2})\s*[:：]\s*(\d{2})",
        re.IGNORECASE,
    )

    def parse_facts(self, raw_text: str) -> InvitationFacts:
        if not raw_text.strip():
            raise MeetingParseError("会议邀请文本不能为空")

        text = raw_text.strip()

        bytedance_facts = self._parse_bytedance_template(text)
        if bytedance_facts is not None:
            return bytedance_facts

        subject = self._extract_subject(text)
        kind = "interview" if "面试" in text else "meeting"
        start_time, end_time = self._extract_time_range(text)
        meeting_url = self._extract_url(text)
        platform = self._extract_platform(text, meeting_url)
        room_number = self._extract_room_number(text)

        if start_time is None or end_time is None:
            raise MeetingParseError("未识别到会议时间，请包含类似：2026/09/03 10:00-10:30")

        assert start_time is not None and end_time is not None
        return InvitationFacts(
            subject=subject,
            kind_hint=kind,
            candidate_name_hint=self._extract_candidate_name(text),
            start_time=start_time,
            end_time=end_time,
            platform=platform,
            room_number=room_number,
            meeting_url=meeting_url,
        )

    def _parse_bytedance_template(self, text: str) -> InvitationFacts | None:
        """Parse ByteDance campus-recruitment invitations that only carry a start time."""
        if not re.search(r"诚邀你参加", text) or not re.search(r"面试时间", text):
            return None

        position_match = re.search(r"诚邀你参加(.+?)岗位的面试", text)
        if not position_match:
            return None
        position = position_match.group(1).strip()

        start_time, end_time = self._extract_time_range(text)
        if start_time is None or end_time is None:
            return None

        subject = f"{position}岗位的面试"
        candidate_name = (
            self._extract_candidate_name(text)
            or self._extract_greeting_name(text)
        )
        meeting_url = self._extract_url(text)
        platform = (
            self._platform_from_url(meeting_url)
            or self._extract_interview_format(text)
            or self._extract_platform(text, meeting_url)
        )

        return InvitationFacts(
            subject=subject,
            kind_hint="interview",
            candidate_name_hint=candidate_name,
            position_hint=position,
            start_time=start_time,
            end_time=end_time,
            platform=platform,
            room_number=None,
            meeting_url=meeting_url,
        )

    def _extract_interview_format(self, text: str) -> str | None:
        match = re.search(r"面试形式\s*[:：]\s*([^\s，,。；;]+)", text)
        return match.group(1).strip() if match else None

    def _extract_greeting_name(self, text: str) -> str | None:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^([\u4e00-\u9fa5A-Za-z·]{2,6})\s*[:：]\s*$", line)
            if match:
                return self._clean_candidate_name(match.group(1))
            break
        return None

    def _extract_subject(self, text: str) -> str | None:
        match = re.search(r"(?:会议主题|会议名称|主题|Subject)\s*[:：]\s*(.+)", text)
        if not match:
            return None
        value = match.group(1).strip().splitlines()[0].strip()
        return value or None

    def _extract_time_range(self, text: str) -> tuple[datetime | None, datetime | None]:
        match = self._RANGE_TIME_PATTERN.search(text)
        if match:
            year, month, day, start_hour, start_minute, end_hour, end_minute = [
                int(item) for item in match.groups()
            ]
            timezone_offset = self._extract_timezone_offset(text)
            try:
                start_time = datetime(year, month, day, start_hour, start_minute, tzinfo=timezone_offset)
                end_time = datetime(year, month, day, end_hour, end_minute, tzinfo=timezone_offset)
            except ValueError:
                return None, None

            if end_time <= start_time:
                end_time += timedelta(days=1)
            return start_time, end_time

        # Fall back to a start-time-only invitation and infer the end time.
        return self._extract_single_time(text)

    def _extract_single_time(self, text: str) -> tuple[datetime | None, datetime | None]:
        match = self._SINGLE_TIME_PATTERN.search(text)
        if not match:
            return None, None
        year, month, day, start_hour, start_minute = [int(item) for item in match.groups()]
        timezone_offset = self._extract_timezone_offset(text)
        try:
            start_time = datetime(year, month, day, start_hour, start_minute, tzinfo=timezone_offset)
        except ValueError:
            return None, None
        end_time = start_time + self.SINGLE_TIME_INFERRED_DURATION
        return start_time, end_time

    def _extract_timezone_offset(self, text: str) -> timezone:
        match = re.search(r"GMT\s*([+-])(\d{1,2})(?::(\d{2}))?", text, re.IGNORECASE)
        if not match:
            return timezone(timedelta(hours=8))
        sign = -1 if match.group(1) == "-" else 1
        hours = int(match.group(2))
        minutes = int(match.group(3) or 0)
        return timezone(sign * timedelta(hours=hours, minutes=minutes))

    def _extract_url(self, text: str) -> str | None:
        for label in self.URL_LABELS:
            match = re.search(
                rf"{label}[:：]\s*(?:\[[^\]]+\]\()?(https?://[^\s\)\]<>]+)",
                text,
                re.IGNORECASE,
            )
            if match:
                return match.group(1).rstrip("，。；）]")
        match = re.search(r"https?://[^\s<>\"']+", text, re.IGNORECASE)
        return match.group(0).rstrip("，。；）]") if match else None

    @staticmethod
    def _platform_from_url(meeting_url: str | None) -> str | None:
        """Return the meeting software indicated by a known meeting URL, if any."""
        if not meeting_url:
            return None
        lowered = meeting_url.lower()
        for keyword, platform in InvitationParser.PLATFORM_RULES:
            if keyword in lowered:
                return platform
        return None

    @staticmethod
    def display_platform(entry: object) -> str:
        """显示用会议软件：优先取已知会议链接域名推断，兼容历史存储记录。"""
        meeting_url = getattr(entry, "meeting_url", None)
        if meeting_url:
            url_platform = InvitationParser._platform_from_url(str(meeting_url))
            if url_platform:
                return url_platform
        return str(getattr(entry, "platform"))

    def _extract_platform(self, text: str, meeting_url: str | None) -> str:
        if "#腾讯会议" in text or "腾讯会议" in text:
            return "腾讯会议"
        if meeting_url:
            for keyword, platform in self.PLATFORM_RULES:
                if keyword in meeting_url.lower():
                    return platform
        if "飞书会议" in text:
            return "飞书会议"
        if "Zoom" in text.lower() or "zoom" in text:
            return "Zoom"
        return "未识别会议平台"

    def _extract_room_number(self, text: str) -> str | None:
        patterns = [
            r"#\s*腾讯会议\s*[:：]\s*([0-9][0-9\- ]{4,})",
            r"(?:会议号|会议号码|Meeting ID|Meeting Number)\s*[:：]?\s*([0-9][0-9\- ]{4,})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = re.sub(r"\s+", "", match.group(1))
                value = re.sub(r"-+", "-", value).strip("-")
                if value:
                    return value
        return None

    CANDIDATE_ROLE_TOKENS = ("实习生", "应届生", "毕业生", "校招", "内推", "社招", "应聘")

    def _extract_candidate_name(self, text: str) -> str | None:
        raw: str | None = None
        for pattern in (
            r"候选人\s*[:：]\s*([^\s，,。；;]+)",
            r"应聘者\s*[:：]\s*([^\s，,。；;]+)",
        ):
            match = re.search(pattern, text)
            if match:
                raw = match.group(1).strip()
                break

        if raw is None:
            subject = self._extract_subject(text) or ""
            match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·]{2,20})的面试", subject)
            if match:
                raw = match.group(1)

        return self._clean_candidate_name(raw)

    def _clean_candidate_name(self, name: str | None) -> str | None:
        """Strip company/role prefixes such as "帝欧水华实习生" from a candidate name."""
        if not name:
            return None
        name = name.strip()
        role_index = -1
        role_len = 0
        for token in self.CANDIDATE_ROLE_TOKENS:
            idx = name.find(token)
            if idx != -1 and (role_index == -1 or idx < role_index):
                role_index, role_len = idx, len(token)
        if role_index != -1:
            after = name[role_index + role_len:].strip()
            name = after or name[:role_index].strip()
        for prefix in ("后端开发", "前端开发", "全栈开发", "产品", "运营"):
            if name.startswith(prefix):
                name = name[len(prefix):]
        for token in self.CANDIDATE_ROLE_TOKENS:
            if name.endswith(token):
                name = name[: -len(token)].strip()
        return name or None
