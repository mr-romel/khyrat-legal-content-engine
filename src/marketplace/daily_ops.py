"""Daily execution planner for the independent Marketplace module.

This module does not discover, log in, submit, or publish on platforms. It
prepares a short ordered task list for the human operator and expires stale
open opportunities safely.
"""
from __future__ import annotations

from datetime import datetime

from marketplace.followup import due_followups, expire_stale, followup_metrics
from marketplace.opportunity_queue import rank_queue


def _parse_time(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def build_daily_plan(state: dict, now: datetime, stale_days: int = 14) -> dict:
    """Return a deterministic, actionable daily plan and update stale items."""
    expired = expire_stale(state, now, stale_days=stale_days)
    due = due_followups(state, now)
    ranked = rank_queue(state)

    # المتابعة التشغيلية اليومية تكون بعد إرسال العرض؛ أما ما قبل الإرسال
    # فيظل ضمن مهام المراجعة حتى لا يظهر مرتين في خطة اليوم.
    submitted_due = [x for x in due if str(x.get("lifecycle", x.get("status", "NEW"))).upper() == "SUBMITTED"]
    due_ids = {str(x.get("id")) for x in submitted_due}
    tasks: list[dict] = []
    seen: set[str] = set()

    # Follow-ups are first because they are time-sensitive.
    for item in submitted_due:
        item_id = str(item.get("id"))
        if item_id in seen:
            continue
        seen.add(item_id)
        tasks.append({
            "type": "FOLLOW_UP",
            "priority": "NOW",
            "id": item_id,
            "title": item.get("title", ""),
            "platform": item.get("platform", ""),
            "source_url": item.get("source_url", ""),
            "offer": item.get("offer", ""),
        })

    # Then approved opportunities that are ready for the human to submit.
    for item in ranked:
        item_id = str(item.get("id"))
        status = str(item.get("lifecycle", item.get("status", "NEW"))).upper()
        if item_id in seen or item_id in due_ids:
            continue
        if status == "APPROVED":
            seen.add(item_id)
            tasks.append({
                "type": "SUBMIT",
                "priority": "HIGH",
                "id": item_id,
                "title": item.get("title", ""),
                "platform": item.get("platform", ""),
                "source_url": item.get("source_url", ""),
                "offer": item.get("offer", ""),
            })

    # Finally, the strongest new/offer-ready opportunities for review.
    for item in ranked:
        item_id = str(item.get("id"))
        status = str(item.get("lifecycle", item.get("status", "NEW"))).upper()
        if item_id in seen:
            continue
        if status in {"NEW", "OFFER_READY", "READY_FOR_REVIEW"}:
            seen.add(item_id)
            tasks.append({
                "type": "REVIEW",
                "priority": "HIGH" if item.get("priority") == "HIGH" else "NORMAL",
                "id": item_id,
                "title": item.get("title", ""),
                "platform": item.get("platform", ""),
                "source_url": item.get("source_url", ""),
                "offer": item.get("offer", ""),
            })

    return {
        "generated_at": now.isoformat(),
        "expired_count": len(expired),
        "tasks": tasks,
        "followup_metrics": followup_metrics(state, now),
        "total_open": sum(
            1 for x in state.get("opportunities", [])
            if str(x.get("lifecycle", x.get("status", ""))).upper() not in {"WON", "LOST", "EXPIRED", "CANCELLED"}
        ),
    }


def task_counts(plan: dict) -> dict:
    counts = {"FOLLOW_UP": 0, "SUBMIT": 0, "REVIEW": 0}
    for task in plan.get("tasks", []):
        kind = task.get("type")
        if kind in counts:
            counts[kind] += 1
    return counts
