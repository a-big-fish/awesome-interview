from datetime import datetime, timezone

from interviewschedule.utils.time_utils import DEFAULT_TIMEZONE, ensure_timezone, now, utc_now


def test_ensure_timezone_assigns_default_timezone_to_naive_datetime():
    assert ensure_timezone(datetime(2026, 9, 10, 10, 0)).tzinfo == DEFAULT_TIMEZONE


def test_ensure_timezone_converts_aware_datetime_to_default_timezone():
    value = ensure_timezone(datetime(2026, 9, 10, 2, 0, tzinfo=timezone.utc))
    assert value.hour == 10
    assert value.tzinfo == DEFAULT_TIMEZONE


def test_now_and_utc_now_are_timezone_aware():
    assert now().tzinfo is not None
    assert utc_now().tzinfo == timezone.utc
