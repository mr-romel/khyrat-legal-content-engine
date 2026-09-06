"""متابعة الفرص: مواعيد المتابعة، التأخير، وانتهاء الفرص.

هذا الملف مستقل عن محرك المحتوى الأساسي وعن الاتصال المباشر بالمنصات.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

OPEN_STATES = {
    "NEW",
    "OFFER_READY",
    "READY_FOR_REVIEW",
    "APPROVED",
    "SUBMITTED",
    "FAILED",
}
TERMINAL_STATES = {"WON", "LOST", "EXPIRED", "CANCELLED"}


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def next_followup(item: dict[str, Any], now: datetime | None = None) -> str | None:
    """يحدد موعد المتابعة التالي حسب حالة الفرصة."""
    state = str(item.get("lifecycle", item.get("status", "NEW"))).upper()
    if state in TERMINAL_STATES:
        return None
    base = _parse(item.get("updated_at")) or _parse(item.get("created_at")) or now
    if base is None:
        return None
    days = 1 if state in {"READY_FOR_REVIEW", "APPROVED", "FAILED"} else 3
    if state == "SUBMITTED":
        days = 2
    return _iso(base + timedelta(days=days))


def prepare_followup(item: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """يضيف بيانات المتابعة دون تغيير حالة الفرصة."""
    due = next_followup(item, now)
    if due:
        item["next_followup_at"] = due
    else:
        item.pop("next_followup_at", None)
    return item


def due_followups(state: dict[str, Any], now: datetime | None = None) -> list[dict[str, Any]]:
    """يعيد الفرص التي حان موعد متابعتها، مرتبة بالأقدم أولاً."""
    now = now or datetime.now().astimezone()
    due: list[dict[str, Any]] = []
    for item in state.get("opportunities", []):
        if str(item.get("lifecycle", item.get("status", "NEW"))).upper() in TERMINAL_STATES:
            continue
        prepare_followup(item, now)
        stamp = _parse(item.get("next_followup_at"))
        if stamp and stamp <= now:
            due.append(item)
    return sorted(due, key=lambda x: x.get("next_followup_at", ""))


def expire_stale(state: dict[str, Any], now: datetime | None = None, stale_days: int = 14) -> list[str]:
    """ينقل الفرص المفتوحة القديمة جداً إلى EXPIRED، ويعيد معرفاتها."""
    if stale_days < 1:
        raise ValueError("عدد أيام انتهاء الصلاحية يجب أن يكون موجباً")
    now = now or datetime.now().astimezone()
    expired: list[str] = []
    cutoff = now - timedelta(days=stale_days)
    for item in state.get("opportunities", []):
        current = str(item.get("lifecycle", item.get("status", "NEW"))).upper()
        if current not in OPEN_STATES:
            continue
        base = _parse(item.get("updated_at")) or _parse(item.get("created_at"))
        if base and base <= cutoff:
            item["lifecycle"] = "EXPIRED"
            item["status"] = "EXPIRED"
            item["expired_at"] = _iso(now)
            item["updated_at"] = _iso(now)
            expired.append(str(item.get("id", "")))
    return expired


def followup_metrics(state: dict[str, Any], now: datetime | None = None) -> dict[str, int]:
    """ملخص تشغيلي للمتابعة."""
    due = due_followups(state, now)
    return {
        "due": len(due),
        "submitted_due": sum(1 for x in due if x.get("lifecycle") == "SUBMITTED"),
        "review_due": sum(1 for x in due if x.get("lifecycle") in {"READY_FOR_REVIEW", "APPROVED"}),
    }
