"""Human-in-the-loop review state machine for Marketplace items."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


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


def transition(item: dict, new_status: str) -> ReviewResult:
    old_status = item.get("status", "DRAFT")
    if new_status not in ALLOWED.get(old_status, set()):
        raise ValueError(f"Invalid Marketplace transition: {old_status} -> {new_status}")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    item["status"] = new_status
    item["reviewed_at"] = now
    return ReviewResult(item.get("id", "unknown"), old_status, new_status, now)
