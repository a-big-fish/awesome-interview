from datetime import date, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator


class RestPeriod(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    start: time
    end: time
    enabled: bool = True

    @model_validator(mode="after")
    def validate_times(self) -> "RestPeriod":
        if self.end <= self.start:
            raise ValueError("休息结束时间必须晚于开始时间")
        return self


def default_breaks() -> list[RestPeriod]:
    return [
        RestPeriod(name="午休", start=time(12), end=time(13)),
        RestPeriod(name="茶歇", start=time(16), end=time(16, 30)),
    ]


class WorkdaySchedule(BaseModel):
    enabled: bool = True
    start: time = time(9)
    end: time = time(19)
    breaks: list[RestPeriod] = Field(default_factory=default_breaks)

    @model_validator(mode="after")
    def validate_periods(self) -> "WorkdaySchedule":
        if self.end <= self.start:
            raise ValueError("下班时间必须晚于上班时间")
        active = sorted((item for item in self.breaks if item.enabled), key=lambda item: item.start)
        for item in active:
            if item.start < self.start or item.end > self.end:
                raise ValueError(f"休息时段“{item.name}”必须在工作时间内")
        for previous, current in zip(active, active[1:]):
            if current.start < previous.end:
                raise ValueError("启用的休息时段不能重叠")
        return self


def default_workweek() -> dict[int, WorkdaySchedule]:
    return {weekday: WorkdaySchedule() for weekday in range(7)}


class EnterpriseCalendarSettings(BaseModel):
    timezone: str = "Asia/Shanghai"
    days: dict[int, WorkdaySchedule] = Field(default_factory=default_workweek)

    @model_validator(mode="after")
    def validate_calendar(self) -> "EnterpriseCalendarSettings":
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("时区无效") from exc
        if set(self.days) != set(range(7)):
            raise ValueError("必须配置星期一至星期日")
        return self

    def for_date(self, selected_date: date) -> WorkdaySchedule:
        """Return the recurring schedule for the selected weekday."""
        return self.days[selected_date.weekday()]
