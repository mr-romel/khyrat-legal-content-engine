"""Opportunity queue management for Marketplace.

Pure business logic: no scraping, login, publishing, or Core imports.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from marketplace.opportunity_engine import rank_opportunity
from marketplace.pricing import suggest_price_usd, validate_price_usd


LIFECYCLE = ("NEW", "OFFER_READY", "READY_FOR_REVIEW", "APPROVED", "SUBMITTED", "WON", "LOST", "EXPIRED", "CANCELLED", "REJECTED", "FAILED")
TERMINAL = {"WON", "LOST", "EXPIRED", "CANCELLED"}


def opportunity_key(platform: str, title: str, description: str) -> str:
    """Stable deduplication key based on normalized source content."""
    def norm(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())
    raw = "|".join((norm(platform), norm(title), norm(description))).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def prepare_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    """Add deterministic queue metadata, including USD-only Mostaql pricing."""
    rank_opportunity(item)
    score = float(item.get("acquisition_score", item.get("match_score", 0)))
    price = item.get("suggested_price_usd")
    if price is None:
        price = suggest_price_usd(score)
    item["suggested_price_usd"] = validate_price_usd(price)
    clarity = 1.0 if len(str(item.get("description", "")).split()) >= 12 else 0.7
    probability = max(0.05, min(0.75, 0.10 + score / 200.0 + (0.05 if clarity == 1.0 else 0)))
    item["win_probability"] = round(probability, 3)
    item["expected_value_usd"] = round(item["suggested_price_usd"] * probability, 2)
    item.setdefault("lifecycle", item.get("status", "NEW"))
    item.setdefault("created_at", "")
    item.setdefault("updated_at", "")
    return item


def find_duplicate(state: dict[str, Any], platform: str, title: str, description: str) -> dict[str, Any] | None:
    key = opportunity_key(platform, title, description)
    for item in state.get("opportunities", []):
        if item.get("dedupe_key") == key:
            return item
    return None


def add_to_queue(state: dict[str, Any], item: dict[str, Any], now: str) -> tuple[dict[str, Any], bool]:
    """Insert an opportunity once; returns (record, created)."""
    platform = str(item.get("platform", "mostaql"))
    title = str(item.get("title", ""))
    description = str(item.get("description", ""))
    duplicate = find_duplicate(state, platform, title, description)
    if duplicate:
        prepare_opportunity(duplicate)
        return duplicate, False
    item["dedupe_key"] = opportunity_key(platform, title, description)
    item["lifecycle"] = item.get("status", "NEW")
    item["created_at"] = now
    item["updated_at"] = now
    prepare_opportunity(item)
    state.setdefault("opportunities", []).insert(0, item)
    return item, True


def transition(item: dict[str, Any], target: str, now: str) -> dict[str, Any]:
    """Apply safe lifecycle transitions used by the private dashboard."""
    current = str(item.get("lifecycle", item.get("status", "NEW")))
    target = str(target).upper()
    if target not in LIFECYCLE:
        raise ValueError(f"حالة غير صالحة: {target}")
    allowed = {
        "NEW": {"OFFER_READY", "REJECTED", "CANCELLED"},
        "OFFER_READY": {"READY_FOR_REVIEW", "REJECTED", "FAILED"},
        "READY_FOR_REVIEW": {"APPROVED", "REJECTED"},
        "APPROVED": {"SUBMITTED", "FAILED", "CANCELLED"},
        "FAILED": {"OFFER_READY", "READY_FOR_REVIEW", "CANCELLED"},
        "REJECTED": {"NEW", "OFFER_READY"},
        "SUBMITTED": {"WON", "LOST", "EXPIRED", "CANCELLED"},
        "WON": set(), "LOST": set(), "EXPIRED": set(), "CANCELLED": set(),
    }
    if target != current and target not in allowed.get(current, set()):
        raise ValueError(f"لا يمكن نقل الفرصة من {current} إلى {target}")
    item["lifecycle"] = target
    item["status"] = target
    item["updated_at"] = now
    if target == "SUBMITTED":
        item["submitted_at"] = now
    if target in TERMINAL:
        item["closed_at"] = now
    return item


def queue_metrics(state: dict[str, Any]) -> dict[str, Any]:
    opportunities = state.get("opportunities", [])
    for item in opportunities:
        prepare_opportunity(item)
    return {
        "total": len(opportunities),
        "high": sum(x.get("priority") == "HIGH" for x in opportunities),
        "medium": sum(x.get("priority") == "MEDIUM" for x in opportunities),
        "low": sum(x.get("priority") == "LOW" for x in opportunities),
        "offer_ready": sum(x.get("lifecycle", x.get("status")) == "OFFER_READY" for x in opportunities),
        "review": sum(x.get("lifecycle", x.get("status")) == "READY_FOR_REVIEW" for x in opportunities),
        "approved": sum(x.get("lifecycle", x.get("status")) == "APPROVED" for x in opportunities),
        "submitted": sum(x.get("lifecycle", x.get("status")) == "SUBMITTED" for x in opportunities),
        "won": sum(x.get("lifecycle", x.get("status")) == "WON" for x in opportunities),
        "lost": sum(x.get("lifecycle", x.get("status")) == "LOST" for x in opportunities),
        "expected_value_usd": round(sum(float(x.get("expected_value_usd", 0)) for x in opportunities if x.get("lifecycle", x.get("status")) not in TERMINAL), 2),
    }


def rank_queue(state: dict[str, Any]) -> list[dict[str, Any]]:
    for item in state.get("opportunities", []):
        prepare_opportunity(item)
    return sorted(state.get("opportunities", []), key=lambda x: (float(x.get("acquisition_score", 0)), float(x.get("expected_value_usd", 0))), reverse=True)
