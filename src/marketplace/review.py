"""Human-in-the-loop review state machine for Marketplace items."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

ALLOWED = {
    "DRAFT": {"READY_FOR_REVIEW"},
    "READY_FOR_REVIEW": {"APPROVED", "REJECTED"},
    "REJECTED": {"DRAFT"},
    "APPROVED": {"PUBLISHED", "SUBMITTED", "FAILED"},
    "PUBLISHED": set(),
    "SUBMITTED": set(),
    "FAILED": {"APPROVED", "DRAFT"},
}


@dataclass(frozen=True)
class ReviewResult:
    item_id: str
    old_status: str
    new_status: str
    reviewed_at: str


def transition(item: dict[str, Any], new_status: str) -> ReviewResult:
    old_status = item.get("status", "DRAFT")
    if new_status not in ALLOWED.get(old_status, set()):
        raise ValueError(f"Invalid Marketplace transition: {old_status} -> {new_status}")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    item["status"] = new_status
    item["reviewed_at"] = now
    return ReviewResult(item.get("id", "unknown"), old_status, new_status, now)


def approve(item: dict[str, Any]) -> ReviewResult:
    """Approve only after the item has explicitly entered READY_FOR_REVIEW."""
    return transition(item, "APPROVED")


def reject(item: dict[str, Any]) -> ReviewResult:
    """Reject a review candidate without deleting its data."""
    return transition(item, "REJECTED")


def mark_ready(item: dict[str, Any]) -> ReviewResult:
    """Move a draft into the human review queue."""
    return transition(item, "READY_FOR_REVIEW")


def metrics(state: dict[str, Any]) -> dict[str, int | float]:
    """Return lightweight Marketplace metrics without touching Core."""
    items = list(state.get("services", [])) + list(state.get("opportunities", []))
    scores = [int(x.get("match_score", 0)) for x in state.get("opportunities", [])]
    return {
        "services": len(state.get("services", [])),
        "portfolio": len(state.get("portfolio", [])),
        "opportunities": len(state.get("opportunities", [])),
        "review_queue": sum(x.get("status") in {"DRAFT", "OFFER_READY", "READY_FOR_REVIEW"} for x in items),
        "approved": sum(x.get("status") in {"APPROVED", "PUBLISHED", "SUBMITTED"} for x in items),
        "failed": sum(x.get("status") == "FAILED" for x in items),
        "avg_match_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
    }
