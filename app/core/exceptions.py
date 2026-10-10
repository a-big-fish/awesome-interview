class MeetingParseError(Exception):
    """Raised when an invitation cannot be parsed into a valid meeting."""


class ScheduleConflictWarning(Exception):
    """A proposed meeting touches configured non-working time and needs confirmation."""

    def __init__(self, warnings: list[str]) -> None:
        self.warnings = warnings
        super().__init__("会议时间与工作或休息时段重叠")


class PersonalEventConflictWarning(Exception):
    """A personal event overlaps an existing event and needs confirmation."""

    def __init__(self, event_titles: list[str]) -> None:
        self.event_titles = event_titles
        super().__init__("日程时间与已有安排重叠")


class EntryNotFoundError(Exception):
    """Raised when a schedule entry does not exist."""


class ResumeParseError(Exception):
    """Raised when a resume PDF cannot be parsed."""


class MyResumeNotFoundError(Exception):
    """Raised when the personal resume profile has not been created."""


class ResumeFileNotFoundError(Exception):
    """Raised when a stored resume PDF or image is unavailable."""


class AIInterviewError(Exception):
    """Raised when an AI interview assistant request cannot be processed."""
