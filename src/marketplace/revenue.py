"""Revenue analytics for the Marketplace module.

Pure calculations over stored opportunity records. No platform access and no Core imports.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


CLOSED = {"WON", "LOST", "EXPIRED", "CANCELLED"}


def record_outcome(item: dict[str, Any], outcome: str, now: str, amount_egp: float | None = None) -> dict[str, Any]:
    outcome = outcome.upper()
    if outcome not in {"WON", "LOST", "EXPIRED", "CANCELLED"}:
        raise ValueError("نتيجة غير صالحة")
    item["lifecycle"] = outcome
    item["status"] = outcome
    item["updated_at"] = now
    item["closed_at"] = now
    if amount_egp is not None:
        if amount_egp < 0:
            raise ValueError("قيمة الصفقة لا يمكن أن تكون سالبة")
        item["actual_revenue_egp"] = round(float(amount_egp), 2)
    elif outcome != "WON":
        item.setdefault("actual_revenue_egp", 0.0)
    return item


def analytics(state: dict[str, Any], monthly_target_egp: float = 20000.0) -> dict[str, Any]:
    items = state.get("opportunities", [])
    submitted = [x for x in items if x.get("submitted_at") or x.get("lifecycle") in {"SUBMITTED", *CLOSED}]
    won = [x for x in items if x.get("lifecycle") == "WON"]
    lost = [x for x in items if x.get("lifecycle") == "LOST"]
    revenue = round(sum(float(x.get("actual_revenue_egp", 0)) for x in won), 2)
    expected_open = round(sum(float(x.get("expected_value_egp", 0)) for x in items if x.get("lifecycle") not in CLOSED), 2)
    decisions = len(won) + len(lost)
    conversion = round(len(won) / decisions * 100, 1) if decisions else 0.0
    by_service: dict[str, dict[str, float]] = defaultdict(lambda: {"won": 0, "revenue": 0.0})
    by_platform: dict[str, dict[str, float]] = defaultdict(lambda: {"won": 0, "revenue": 0.0})
    for x in won:
        service = str(x.get("service_title") or x.get("matched_service") or "غير محدد")
        platform = str(x.get("platform", "غير محدد"))
        amount = float(x.get("actual_revenue_egp", 0))
        by_service[service]["won"] += 1
        by_service[service]["revenue"] += amount
        by_platform[platform]["won"] += 1
        by_platform[platform]["revenue"] += amount
    remaining = max(0.0, monthly_target_egp - revenue)
    return {
        "target_egp": round(monthly_target_egp, 2),
        "revenue_egp": revenue,
        "remaining_to_target_egp": round(remaining, 2),
        "target_progress_pct": round(min(100.0, revenue / monthly_target_egp * 100), 1) if monthly_target_egp else 0.0,
        "submitted": len(submitted),
        "won": len(won),
        "lost": len(lost),
        "conversion_pct": conversion,
        "expected_open_egp": expected_open,
        "by_service": {k: {"won": int(v["won"]), "revenue": round(v["revenue"], 2)} for k, v in by_service.items()},
        "by_platform": {k: {"won": int(v["won"]), "revenue": round(v["revenue"], 2)} for k, v in by_platform.items()},
    }
