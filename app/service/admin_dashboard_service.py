"""Read-only aggregate statistics for the administrator dashboard."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.mapper.base_auth_mapper import BaseAuthMapper
from app.mapper.base_interview_experience_mapper import BaseInterviewExperienceMapper


def build_admin_dashboard(auth: BaseAuthMapper,
                          experiences: BaseInterviewExperienceMapper,
                          today: date | None = None) -> dict:
    """Combine daily database counts into totals and a 30-day chart series."""
    today = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    registrations = auth.registration_counts_by_day()
    notes = experiences.experience_counts_by_day()
    days = [today - timedelta(days=offset) for offset in range(29, -1, -1)]
    series = [{
        "day": day,
        "label": day.strftime("%m/%d"),
        "users": registrations.get(day, 0),
        "public": notes.get(day, (0, 0))[0],
        "private": notes.get(day, (0, 0))[1],
    } for day in days]
    total_users = sum(registrations.values())
    total_public = sum(public for public, _ in notes.values())
    total_private = sum(private for _, private in notes.values())
    total_notes = total_public + total_private
    maximum = max((max(row["users"], row["public"] + row["private"]) for row in series), default=0)
    for row in series:
        row["user_height"] = round(100 * row["users"] / maximum) if maximum else 0
        row["public_height"] = round(100 * row["public"] / maximum) if maximum else 0
        row["private_height"] = round(100 * row["private"] / maximum) if maximum else 0
    return {
        "total_users": total_users,
        "total_notes": total_notes,
        "total_public": total_public,
        "total_private": total_private,
        "recent_users": sum(row["users"] for row in series),
        "recent_notes": sum(row["public"] + row["private"] for row in series),
        "public_percent": round(100 * total_public / total_notes) if total_notes else 0,
        "series": series,
        "today": today,
    }
