from __future__ import annotations

from datetime import date, timedelta
import hashlib

START_HOUR = 10
END_HOUR = 22


def _daily_hour(value: date) -> int:
    """Return one stable, variable hourly Cairo slot for the given date."""
    hours = list(range(START_HOUR, END_HOUR + 1))
    digest = hashlib.sha256(value.isoformat().encode("utf-8")).digest()
    hour = hours[digest[0] % len(hours)]

    # Avoid repeating the exact hour on consecutive days when possible.
    previous = value - timedelta(days=1)
    previous_digest = hashlib.sha256(previous.isoformat().encode("utf-8")).digest()
    previous_hour = hours[previous_digest[0] % len(hours)]
    if hour == previous_hour:
        hour = hours[(hours.index(hour) + 1 + digest[1] % (len(hours) - 1)) % len(hours)]
    return hour


def daily_posting_times(year: int, month: int, day: int) -> tuple[str]:
    """Return exactly one stable, variable hourly Cairo slot for the given date."""
    current = date(year, month, day)
    return (f"{_daily_hour(current):02d}:00",)
