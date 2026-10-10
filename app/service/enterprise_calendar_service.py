from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.mapper.base_enterprise_calendar_mapper import BaseEnterpriseCalendarMapper
from app.model.enterprise_calendar import EnterpriseCalendarSettings


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


class EnterpriseCalendarService:
    """Apply the enterprise workweek to calendar shading and soft warnings."""

    def __init__(self, mapper: BaseEnterpriseCalendarMapper) -> None:
        self.mapper = mapper

    def get_settings(self) -> EnterpriseCalendarSettings:
        return self.mapper.get() or EnterpriseCalendarSettings()

    def save_settings(self, settings: EnterpriseCalendarSettings) -> EnterpriseCalendarSettings:
        return self.mapper.save(settings)

    def shaded_blocks(self, selected_date: date, visible_start: int, visible_end: int) -> list[dict]:
        """Return clipped visual blocks, expressed in minutes from local midnight."""
        day = self.get_settings().for_date(selected_date)
        segments: list[tuple[str, int, int, str]] = []
        if not day.enabled:
            segments.append(("非工作日", 0, 1440, "off-hours"))
        else:
            work_start, work_end = _minutes(day.start), _minutes(day.end)
            segments.extend([
                ("工作时间外", 0, work_start, "off-hours"),
                ("下班后", work_end, 1440, "off-hours"),
            ])
            segments.extend(
                (item.name, _minutes(item.start), _minutes(item.end), "rest")
                for item in day.breaks if item.enabled
            )
        return [
            {
                "label": label,
                "start_minutes": max(start, visible_start),
                "duration_minutes": min(end, visible_end) - max(start, visible_start),
                "kind": kind,
            }
            for label, start, end, kind in segments
            if min(end, visible_end) > max(start, visible_start)
        ]

    def overlap_warnings(self, start: datetime, end: datetime) -> list[str]:
        """Describe work and rest periods touched by a proposed meeting."""
        settings = self.get_settings()
        zone = ZoneInfo(settings.timezone)
        local_start, local_end = start.astimezone(zone), end.astimezone(zone)
        warnings: list[str] = []
        day = local_start.date()
        while day <= local_end.date():
            day_start = datetime.combine(day, time.min, tzinfo=zone)
            next_day = day_start + timedelta(days=1)
            schedule = settings.for_date(day)
            if not schedule.enabled:
                segments = [("非工作日", day_start, next_day)]
            else:
                work_start = datetime.combine(day, schedule.start, tzinfo=zone)
                work_end = datetime.combine(day, schedule.end, tzinfo=zone)
                segments = [
                    ("工作时间外", day_start, work_start),
                    ("下班后", work_end, next_day),
                ]
                segments.extend(
                    (item.name, datetime.combine(day, item.start, tzinfo=zone),
                     datetime.combine(day, item.end, tzinfo=zone))
                    for item in schedule.breaks if item.enabled
                )
            for name, segment_start, segment_end in segments:
                if local_start < segment_end and local_end > segment_start:
                    warnings.append(
                        f"{day.isoformat()} {name} "
                        f"{segment_start.strftime('%H:%M')}-{segment_end.strftime('%H:%M')}"
                    )
            day += timedelta(days=1)
        return warnings
