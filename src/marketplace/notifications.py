"""Notification planning without platform automation or external credentials."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from marketplace.daily_ops import build_daily_plan
from marketplace.followup import due_followups
from marketplace.opportunity_queue import rank_queue


def build_notifications(state: dict[str, Any], now: datetime) -> list[dict[str, str]]:
    """Build local/in-app notification records for the human operator."""
    out: list[dict[str, str]] = []
    due = due_followups(state, now)
    if due:
        out.append({"type": "FOLLOW_UP", "priority": "HIGH", "title": f"لديك {len(due)} متابعة مستحقة", "body": "ابدأ بالفرص المرسلة قبل أي مهمة جديدة."})
    plan = build_daily_plan(state, now)
    review_count = sum(x.get("type") == "REVIEW" for x in plan.get("tasks", []))
    submit_count = sum(x.get("type") == "SUBMIT" for x in plan.get("tasks", []))
    if review_count:
        out.append({"type": "REVIEW", "priority": "HIGH", "title": f"{review_count} فرصة تحتاج مراجعة", "body": "راجع العرض قبل اعتماده."})
    if submit_count:
        out.append({"type": "SUBMIT", "priority": "HIGH", "title": f"{submit_count} فرصة جاهزة للتنفيذ", "body": "افتح المشروع ونفّذ الإرسال يدويًا على المنصة."})
    ranked = rank_queue(state)
    if ranked:
        best = ranked[0]
        out.append({"type": "BEST_OPPORTUNITY", "priority": "NORMAL", "title": "أفضل فرصة الآن", "body": str(best.get("title", "فرصة جديدة"))})
    return out


def notification_metrics(state: dict[str, Any], now: datetime) -> dict[str, int]:
    items = build_notifications(state, now)
    return {
        "total": len(items),
        "high": sum(x.get("priority") == "HIGH" for x in items),
        "follow_up": sum(x.get("type") == "FOLLOW_UP" for x in items),
        "review": sum(x.get("type") == "REVIEW" for x in items),
        "submit": sum(x.get("type") == "SUBMIT" for x in items),
    }
