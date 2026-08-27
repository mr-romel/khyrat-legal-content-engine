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

    # Telegram is an auxiliary notification channel. A Telegram outage,
    # message-size problem, or bot error must never change the publication result.
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
        # Never let Telegram failure roll back or mark social publication as failed.
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


def _wait_until_due(target_datetime, *, tolerance_minutes: int = 2):
    now = now_cairo()
    if target_datetime is None:
        return False
    delta = target_datetime - now
    return delta.total_seconds() <= tolerance_minutes * 60


def _should_process_row(row: dict[str, str]) -> bool:
    status = str(row.get("الحالة", "")).strip().upper()
    if status in {"PUBLISHED", "CANCELLED"}:
        return False
    target = _smart_target_datetime(row)
    if target is None:
        return False
    return _wait_until_due(target)


def _process_due_rows(*args, **kwargs):
    return production_main._process_due_rows(*args, **kwargs)


def main() -> None:
    print("=" * 70)
    print("KHYRAT LEGAL CONTENT ENGINE - V2 SMART SOCIAL PIPELINE")
    print("=" * 70)
    current = now_cairo()
    print(f"Current Cairo time: {current.isoformat()}")
    production_main.main()


if __name__ == "__main__":
    main()
