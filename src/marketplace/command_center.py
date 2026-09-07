"""Revenue command center for the independent Marketplace module."""
from __future__ import annotations

from typing import Any

from marketplace.revenue import analytics

MONTHLY_TARGET_EGP = 20_000.0


def build_command_center(state: dict[str, Any], month: str | None = None) -> dict[str, Any]:
    """Return decision-ready revenue metrics and the next numeric target."""
    data = analytics(state, monthly_target_egp=MONTHLY_TARGET_EGP, month=month)
    remaining = float(data["remaining_to_target_egp"])
    average = float(data["average_win_egp"])
    deals_needed = 0 if remaining <= 0 else (int((remaining + max(average, 1) - 1) // max(average, 1)) if average else 0)
    if data["won"] == 0:
        deals_needed = 0
    progress = float(data["target_progress_pct"])
    return {
        **data,
        "deals_needed_at_average_win": deals_needed,
        "target_reached": progress >= 100.0,
        "headline": "الهدف الشهري تحقق" if progress >= 100 else f"متبقي {remaining:,.0f} جنيه للوصول إلى 20,000",
    }


def next_action(center: dict[str, Any]) -> str:
    if center.get("target_reached"):
        return "حافظ على معدل الفوز وابدأ في رفع متوسط قيمة الصفقة."
    if center.get("won", 0) == 0:
        return "ركز على فرص عالية الأولوية وسجّل أول فوز قابل للقياس."
    return f"استهدف {center.get('deals_needed_at_average_win', 0)} فوز إضافي بمتوسط الصفقة الحالي."
