from datetime import datetime
from zoneinfo import ZoneInfo


CAIRO_TZ = ZoneInfo("Africa/Cairo")


def now_cairo() -> datetime:
    return datetime.now(CAIRO_TZ)


def normalize_status(value: str) -> str:
    return (value or "").strip().upper()


def parse_date(value: str):
    value = (value or "").strip()
    if not value:
        return None

    formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise ValueError(
        f"Invalid date '{value}'. Use YYYY-MM-DD, e.g. 2026-08-16."
    )


def parse_time(value: str):
    value = (value or "").strip()
    if not value:
        return None

    formats = ["%H:%M", "%H:%M:%S"]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue

    raise ValueError(
        f"Invalid time '{value}'. Use HH:MM, e.g. 20:00."
    )


def _parse_last_run(value: str):
    value = (value or "").strip()
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_due(row: dict, current: datetime) -> bool:
    status = normalize_status(row.get("الحالة", "READY"))
    schedule_type = row.get("نوع الجدولة", "DATE_TIME").strip().upper()

    # One-time items are processed only when READY/FAILED.
    # Generated/published statuses are intentionally ignored.
    if schedule_type == "DATE_TIME":
        if status not in {"READY", "FAILED"}:
            return False
    else:
        # Recurring items may remain READY_FOR_SOCIAL_PUBLISH after generation.
        if status not in {
            "READY",
            "FAILED",
            "READY_FOR_SOCIAL_PUBLISH",
            "NEEDS_REVIEW",
        }:
            return False

    target_date = parse_date(row.get("تاريخ النشر", ""))
    target_time = parse_time(row.get("ساعة النشر", ""))

    if target_date is None or target_time is None:
        return False

    last_run = _parse_last_run(row.get("وقت آخر تشغيل", ""))

    # Never run the same recurring row more than once on the same Cairo date.
    if schedule_type != "DATE_TIME" and last_run is not None:
        last_run_cairo = last_run.astimezone(CAIRO_TZ)
        if last_run_cairo.date() == current.date():
            return False

    if current.date() < target_date:
        return False

    if schedule_type == "DAILY_ODD" and current.day % 2 == 0:
        return False

    if schedule_type == "DAILY_EVEN" and current.day % 2 != 0:
        return False

    # For DATE_TIME: allow the run within a one-hour window after the target.
    # This is robust against GitHub schedule jitter.
    # For recurring schedules: the same one-hour window is used each eligible day.
    target_dt = current.replace(
        hour=target_time.hour,
        minute=target_time.minute,
        second=0,
        microsecond=0,
    )

    seconds_since_target = (current - target_dt).total_seconds()
    return 0 <= seconds_since_target < 3600


def sheet_name_from_range(sheet_range: str) -> str:
    if "!" not in sheet_range:
        return "Content"
    return sheet_range.split("!", 1)[0].strip()
