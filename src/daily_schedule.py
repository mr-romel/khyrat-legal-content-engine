from __future__ import annotations

from datetime import date, timedelta
import hashlib

START_HOUR = 10
END_HOUR = 22


def daily_posting_times(year: int, month: int, day: int) -> tuple[str, str]:
    """Return two stable, different hourly Cairo slots for the given date."""
    hours = list(range(START_HOUR, END_HOUR + 1))
    digest = hashlib.sha256(f"{year:04d}-{month:02d}-{day:02d}".encode("utf-8")).digest()
    first = hours[digest[0] % len(hours)]
    second = hours[digest[1] % len(hours)]
    if second == first:
        second = hours[(hours.index(second) + 1 + digest[2] % (len(hours) - 1)) % len(hours)]

    previous = date(year, month, day) - timedelta(days=1)
    previous_digest = hashlib.sha256(previous.isoformat().encode("utf-8")).digest()
    previous_first = hours[previous_digest[0] % len(hours)]
    previous_second = hours[previous_digest[1] % len(hours)]
    if previous_second == previous_first:
        previous_second = hours[(hours.index(previous_second) + 1 + previous_digest[2] % (len(hours) - 1)) % len(hours)]
    if {first, second} == {previous_first, previous_second}:
        second = hours[(hours.index(second) + 1) % len(hours)]
        if second == first:
            second = hours[(hours.index(second) + 1) % len(hours)]

    return tuple(f"{hour:02d}:00" for hour in sorted((first, second)))
