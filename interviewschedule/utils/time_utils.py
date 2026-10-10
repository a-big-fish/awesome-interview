from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = ZoneInfo("Asia/Shanghai")


def ensure_timezone(value: datetime) -> datetime:
    """Give naive datetimes the project default timezone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=DEFAULT_TIMEZONE)
    return value.astimezone(DEFAULT_TIMEZONE)


def now() -> datetime:
    return datetime.now(DEFAULT_TIMEZONE)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
