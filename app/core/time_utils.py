"""Compatibility exports; canonical implementation lives in interviewschedule.utils."""

from interviewschedule.utils.time_utils import (
    DEFAULT_TIMEZONE,
    ensure_timezone,
    now,
    utc_now,
)

__all__ = ["DEFAULT_TIMEZONE", "ensure_timezone", "now", "utc_now"]
