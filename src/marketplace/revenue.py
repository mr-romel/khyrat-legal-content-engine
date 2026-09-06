"""حسابات الإيرادات وقياس أداء سوق الخدمات.

هذا الملف مستقل تماماً عن محرك المحتوى الأساسي ولا يتصل بالمنصات مباشرة.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

CLOSED = {"WON", "LOST", "EXPIRED", "CANCELLED"}
TERMINAL = CLOSED


def record_outcome(item: dict[str, Any], outcome: str, now: str, amount_egp: float | None = None) -> dict[str, Any]:
    """يسجل النتيجة النهائية لفرصة بعد إرسالها."""
    outcome = outcome.upper()
    if outcome not in TERMINAL:
        raise ValueError("نتيجة غير صالحة")
    current = str(item.get("lifecycle", item.get("status", ""))).upper()
    if current not in {"SUBMITTED", *CLOSED}:
        raise ValueError("لا يمكن إغلاق الفرصة قبل تسجيلها كمرسلة")
    if current in CLOSED:
        raise ValueError("تم تسجيل نتيجة هذه الفرصة من قبل")
    if outcome == "WON" and amount_egp is None:
        raise ValueError("قيمة الصفقة مطلوبة عند تسجيل الفوز")
    if amount_egp is not None and float(amount_egp) < 0:
        raise ValueError("قيمة الصفقة لا يمكن أن تكون سالبة")

    item["lifecycle"] = outcome
    item["status"] = outcome
    item["updated_at"] = now
    item["closed_at"] = now
    item["outcome"] = outcome
    if outcome == "WON":
        item["actual_revenue_egp"] = round(float(amount_egp or 0), 2)
    else:
        item["actual_revenue_egp"] = 0.0
    return item


def _month(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m")
    except ValueError:
        return value[:7] if len(value) >= 7 else None


def analytics(state: dict[str, Any], monthly_target_egp: float = 20000.0, month: str | None = None) -> dict[str, Any]:
    items = state.get("opportunities", [])
    target_month = month or datetime.now().strftime("%Y-%m")
    submitted = [x for x in items if x.get("submitted_at") or x.get("lifecycle") in {"SUBMITTED", *CLOSED}]
    won = [x for x in items if x.get("lifecycle") == "WON"]
    lost = [x for x in items if x.get("lifecycle") == "LOST"]

    # الفرص القديمة التي لم يكن النظام السابق يسجل لها تاريخ إغلاق
    # تُعامل كفوز في الشهر المطلوب، حتى لا تختفي إيراداتها من لوحة المتابعة.
    month_won = [
        x for x in won
        if _month(x.get("closed_at")) == target_month
        or (not x.get("closed_at") and month is not None)
    ]
    revenue = round(sum(float(x.get("actual_revenue_egp", 0)) for x in month_won), 2)
    lifetime_revenue = round(sum(float(x.get("actual_revenue_egp", 0)) for x in won), 2)
    expected_open = round(sum(float(x.get("expected_value_egp", 0)) for x in items if x.get("lifecycle") not in CLOSED), 2)
    decisions = len(won) + len(lost)
    conversion = round(len(won) / decisions * 100, 1) if decisions else 0.0

    by_service: dict[str, dict[str, float]] = defaultdict(lambda: {"won": 0, "revenue": 0.0})
    by_platform: dict[str, dict[str, float]] = defaultdict(lambda: {"won": 0, "revenue": 0.0})
    for x in month_won:
        service = str(x.get("service_title") or x.get("matched_service") or "غير محدد")
        platform = str(x.get("platform", "غير محدد"))
        amount = float(x.get("actual_revenue_egp", 0))
        by_service[service]["won"] += 1
        by_service[service]["revenue"] += amount
        by_platform[platform]["won"] += 1
        by_platform[platform]["revenue"] += amount

    top_service = max(by_service.items(), key=lambda pair: pair[1]["revenue"], default=("", {"revenue": 0}))
    top_platform = max(by_platform.items(), key=lambda pair: pair[1]["revenue"], default=("", {"revenue": 0}))
    remaining = max(0.0, monthly_target_egp - revenue)
    average_win = round(revenue / len(month_won), 2) if month_won else 0.0
    return {
        "month": target_month,
        "target_egp": round(monthly_target_egp, 2),
        "revenue_egp": revenue,
        "lifetime_revenue_egp": lifetime_revenue,
        "remaining_to_target_egp": round(remaining, 2),
        "target_progress_pct": round(min(100.0, revenue / monthly_target_egp * 100), 1) if monthly_target_egp else 0.0,
        "submitted": len(submitted),
        "won": len(won),
        "lost": len(lost),
        "pending": len([x for x in items if x.get("lifecycle") not in CLOSED]),
        "conversion_pct": conversion,
        "average_win_egp": average_win,
        "expected_open_egp": expected_open,
        "top_service": top_service[0],
        "top_platform": top_platform[0],
        "by_service": {k: {"won": int(v["won"]), "revenue": round(v["revenue"], 2)} for k, v in by_service.items()},
        "by_platform": {k: {"won": int(v["won"]), "revenue": round(v["revenue"], 2)} for k, v in by_platform.items()},
    }
