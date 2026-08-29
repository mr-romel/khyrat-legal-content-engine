from __future__ import annotations

from datetime import datetime, timedelta

import gemini
import main as production_main
from gemini_runtime import generate_post as resilient_generate_post
from telegram_publication import send_single_publication_message, send_single_status_message
from utils import now_cairo, parse_date, parse_time


gemini.generate_post = resilient_generate_post
_original_prepare_editorial_assets = production_main._prepare_editorial_assets
_latest_editorial: dict = {}


def _capture_editorial_assets(*args, **kwargs):
    global _latest_editorial
    result = _original_prepare_editorial_assets(*args, **kwargs)
    _latest_editorial = dict(result)
    _latest_editorial["legal_sources"] = str(kwargs.get("legal_sources", "") or "").strip()
    return result


def _single_telegram_notify(text: str) -> None:
    compact = str(text or "").strip()
    try:
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
                    legal_sources=str(_latest_editorial.get("legal_sources", "")),
                    status_text="Facebook + LinkedIn: تم النشر بنجاح",
                )
            else:
                send_single_status_message(text=compact)
            return
        send_single_status_message(text=compact)
    except Exception as exc:
        print(f"Telegram notification failed (non-blocking): {exc}")


def _suppress_linkedin_diagnostic(**kwargs) -> None:
    return None


def _smart_target_datetime(row: dict[str, str]):
    target_date = parse_date(row.get("تاريخ النشر", ""))
    target_time = parse_time(row.get("ساعة النشر", ""))
    if target_date is None or target_time is None:
        return None
    cairo_now = now_cairo()
    return datetime(target_date.year, target_date.month, target_date.day, target_time.hour, target_time.minute, 0, tzinfo=cairo_now.tzinfo)


def _smart_is_due(row: dict[str, str], current) -> bool:
    status = str(row.get("الحالة", "READY")).strip().upper()
    if status not in {"READY", "READY_FOR_SOCIAL_PUBLISH", "FAILED", "PARTIAL_FAILED"}:
        return False
    target = _smart_target_datetime(row)
    if target is None or current < target:
        return False
    return current - target <= timedelta(hours=16)


def _smart_failed_retry(row: dict[str, str], current) -> bool:
    return str(row.get("الحالة", "")).strip().upper() in {"FAILED", "PARTIAL_FAILED"} and _smart_is_due(row, current)


production_main._prepare_editorial_assets = _capture_editorial_assets
production_main.notify = _single_telegram_notify
production_main.notify_linkedin_interaction = _suppress_linkedin_diagnostic
production_main._is_due = _smart_is_due
production_main._failed_retry = _smart_failed_retry
production_main.main()
