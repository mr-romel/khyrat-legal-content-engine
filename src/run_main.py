from __future__ import annotations

from datetime import datetime, timedelta

import gemini
import main as production_main
from gemini_runtime import generate_post as resilient_generate_post
from telegram_publication import send_single_publication_message, send_single_status_message
from utils import now_cairo, parse_date, parse_time


# main.py imports generate_post from the gemini module. Patch that symbol before
# running the production pipeline so the existing retries and fallback remain active.
gemini.generate_post = resilient_generate_post


# Capture the final post after the comprehensive legal/editorial gate. This is
# the exact version sent to the social publishers and to the Telegram video package.
_original_prepare_editorial_assets = production_main._prepare_editorial_assets
_latest_editorial: dict = {}


def _capture_editorial_assets(*args, **kwargs):
    global _latest_editorial
    result = _original_prepare_editorial_assets(*args, **kwargs)
    _latest_editorial = dict(result)
    return result


def _single_telegram_notify(text: str) -> None:
    """Send Telegram notifications without ever turning a successful publication into a failed run."""
    compact = str(text or "").strip()
    try:
        # Intermediate diagnostics are intentionally suppressed. The final
        # publication result is the single Telegram package for the run.
        if compact.startswith(("🚨", "❌", "🟡")):
            return

        if compact.startswith("🟠"):
            send_single_status_message(text=compact)
            return

        if compact.startswith("✅"):
            marker = "تم نشر:"
            topic = compact.split(marker, 1)[1].split("\n", 1)[0].strip() if marker in compact else "غير متاح"
            post = str(_latest_editorial.get("facebook_post", "")).strip()
            if post:
                send_single_publication_message(
                    topic=topic,
                    post=post,
                    status_text="Facebook + LinkedIn: تم النشر بنجاح",
                )
            else:
                send_single_status_message(text=compact)
            return

        send_single_status_message(text=compact)
    except Exception as exc:
        # Telegram is auxiliary; notification failure must never affect publishing.
        print(f"Telegram notification failed (non-blocking): {exc}")


def _suppress_linkedin_diagnostic(**kwargs) -> None:
    """Keep LinkedIn interaction diagnostics in GitHub logs, not extra Telegram messages."""
    return None


def _smart_target_datetime(row: dict[str, str]):
    target_date = parse_date(row.get("تاريخ النشر", ""))
    target_time = parse_time(row.get("ساعة النشر", ""))
    if target_date is None or target_time is None:
        return None

    cairo_now = now_cairo()
    cairo_zone = cairo_now.tzinfo
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        target_time.hour,
        target_time.minute,
        0,
        tzinfo=cairo_zone,
    )


def _smart_is_due(row: dict[str, str], current) -> bool:
    """Return True for scheduled posts that are due and still safely catch-up eligible.

    Rules:
    - READY, READY_FOR_SOCIAL_PUBLISH, FAILED and PARTIAL_FAILED are eligible.
    - Future posts are never selected early.
    - A missed post remains eligible for catch-up for 16 hours after its exact
      scheduled time. This covers the full 10:00-00:00 publishing window and
      a reasonable overnight recovery without publishing stale content days later.
    - The exact scheduled date/time is used; the old implementation incorrectly
      rebuilt the target timestamp on the current date, which could make a missed
      post disappear after the one-hour window.
    """
    status = str(row.get("الحالة", "READY")).strip().upper()
    if status not in {"READY", "READY_FOR_SOCIAL_PUBLISH", "FAILED", "PARTIAL_FAILED"}:
        return False

    target = _smart_target_datetime(row)
    if target is None:
        return False

    if current < target:
        return False

    age = current - target
    return age <= timedelta(hours=16)


def _smart_failed_retry(row: dict[str, str], current) -> bool:
    """Retry only failed rows that are actually due under the same catch-up policy."""
    status = str(row.get("الحالة", "")).strip().upper()
    if status not in {"FAILED", "PARTIAL_FAILED"}:
        return False
    return _smart_is_due(row, current)


production_main._prepare_editorial_assets = _capture_editorial_assets
production_main.notify = _single_telegram_notify
production_main.notify_linkedin_interaction = _suppress_linkedin_diagnostic

# Replace the old one-hour Due policy with the complete catch-up policy above.
production_main._is_due = _smart_is_due
production_main._failed_retry = _smart_failed_retry

production_main.main()
