"""Marketplace production pipeline helpers.

This module stays inside Marketplace and never imports Core modules.
It prepares a useful initial catalog, portfolio set, and offer quality checks.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from marketplace.catalog import prioritized_topics
from marketplace_mvp import add_opportunity, generate_portfolio, generate_service, build_offer


def ensure_initial_assets(state: dict[str, Any]) -> dict[str, int]:
    """Create the initial Khamsat service catalog and four portfolio samples.

    Existing records are preserved; IDs are used for idempotency.
    """
    services = state.setdefault("services", [])
    portfolio = state.setdefault("portfolio", [])
    service_ids = {x.get("id") for x in services}
    portfolio_ids = {x.get("id") for x in portfolio}

    created_services = 0
    for topic in prioritized_topics():
        item = generate_service(topic)
        if item.id not in service_ids:
            services.append(asdict(item))
            service_ids.add(item.id)
            created_services += 1

    portfolio_topics = prioritized_topics()[:4]
    created_portfolio = 0
    for topic in portfolio_topics:
        item = generate_portfolio(topic)
        if item.id not in portfolio_ids:
            portfolio.append(asdict(item))
            portfolio_ids.add(item.id)
            created_portfolio += 1

    for opportunity in state.get("opportunities", []):
        if not opportunity.get("offer"):
            opportunity["offer"] = build_offer(opportunity)
            opportunity["status"] = "OFFER_READY"

    return {"services_created": created_services, "portfolio_created": created_portfolio}


def ingest_mostaql_opportunity(
    state: dict[str, Any], title: str, description: str
) -> dict[str, Any]:
    """Add a manually captured Mostaql project to the review queue.

    There is deliberately no scraping/login/submission here until an official
    supported integration is verified.
    """
    item = add_opportunity(state, title.strip(), description.strip())
    item_dict = next(x for x in state["opportunities"] if x.get("id") == item.id)
    item_dict["offer"] = build_offer(item_dict)
    item_dict["status"] = "OFFER_READY"
    return item_dict


def offer_quality(opportunity: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic pre-review checks on a generated offer."""
    offer = str(opportunity.get("offer", "")).strip()
    platform = str(opportunity.get("platform", "mostaql")).lower()
    issues: list[str] = []
    checks = {
        "has_offer": bool(offer),
        "has_duration": "المدة المقترحة:" in offer,
        "has_budget": "الميزانية المقترحة:" in offer,
        "has_scope": "نطاق العمل" in offer,
        "no_external_links": not any(token in offer.lower() for token in ("http://", "https://", "www.")),
    }
    if not checks["has_offer"]:
        issues.append("العرض فارغ")
    if not checks["has_duration"]:
        issues.append("المدة غير واضحة")
    if not checks["has_budget"]:
        issues.append("الميزانية غير واضحة")
    if not checks["has_scope"]:
        issues.append("نطاق العمل غير موضح")
    if platform == "mostaql" and not checks["no_external_links"]:
        issues.append("العرض يحتوي على رابط خارجي")
    checks["passed"] = not issues
    return {"passed": not issues, "checks": checks, "issues": issues}


def summarize_pipeline(state: dict[str, Any]) -> dict[str, Any]:
    opportunities = state.get("opportunities", [])
    quality = [offer_quality(x) for x in opportunities if x.get("offer")]
    return {
        "services": len(state.get("services", [])),
        "portfolio": len(state.get("portfolio", [])),
        "opportunities": len(opportunities),
        "ready_offers": sum(x.get("status") == "OFFER_READY" for x in opportunities),
        "quality_passed": sum(x.get("passed") for x in quality),
        "quality_failed": sum(not x.get("passed") for x in quality),
        "avg_match_score": round(sum(x.get("match_score", 0) for x in opportunities) / len(opportunities), 1) if opportunities else 0.0,
    }
