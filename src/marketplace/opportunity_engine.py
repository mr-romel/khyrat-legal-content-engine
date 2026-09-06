"""Opportunity ranking and queue helpers for Marketplace.

No platform login, scraping, or submission lives here. Inputs can come from
manual capture now and a future verified adapter later.
"""
from __future__ import annotations

from typing import Any

LEGAL_TERMS = {
    "عقد": 18, "عقود": 18, "مراجعة": 12, "صياغة": 12, "محامي": 14,
    "محاماة": 14, "قانوني": 14, "قانونية": 14, "شركة": 10, "شركات": 10,
    "عمل": 8, "عمال": 8, "وظائف": 5, "شراكة": 10, "اتفاقية": 12,
    "لائحة": 10, "سياسة": 8, "استشارة": 12, "نزاع": 7, "تجاري": 10,
}


def _text(item: dict[str, Any]) -> str:
    return f"{item.get('title', '')} {item.get('description', '')}".strip().lower()


def rank_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    """Add a deterministic acquisition score and explain the decision."""
    text = _text(item)
    matched = [term for term in LEGAL_TERMS if term in text]
    legal_fit = min(55, sum(LEGAL_TERMS[t] for t in matched))
    clarity = 15 if len(str(item.get("description", ""))) >= 160 else 8
    score = min(100, legal_fit + clarity + int(item.get("match_score", 0)) * 3 // 10)

    reasons: list[str] = []
    if matched:
        reasons.append("تخصص قانوني مناسب: " + "، ".join(matched[:6]))
    if clarity == 15:
        reasons.append("وصف المشروع واضح بما يكفي لبناء عرض مخصص")
    else:
        reasons.append("وصف المشروع مختصر؛ يحتاج قراءة بشرية قبل التقديم")

    if score >= 75:
        priority = "HIGH"
        recommendation = "قدّم بعد مراجعة العرض والسعر"
    elif score >= 55:
        priority = "MEDIUM"
        recommendation = "راجع المشروع أولًا؛ قد يحتاج تخصيصًا إضافيًا"
    else:
        priority = "LOW"
        recommendation = "لا تقدّم إلا إذا ظهرت معلومة إضافية ترفع الملاءمة"

    item["acquisition_score"] = score
    item["priority"] = priority
    item["ranking_reasons"] = reasons
    item["recommendation"] = recommendation
    return item


def rank_queue(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Rank all opportunities without changing their platform status."""
    items = [rank_opportunity(x) for x in state.get("opportunities", [])]
    return sorted(items, key=lambda x: (x.get("acquisition_score", 0), x.get("match_score", 0)), reverse=True)


def queue_metrics(state: dict[str, Any]) -> dict[str, int]:
    ranked = rank_queue(state)
    return {
        "high_priority": sum(x.get("priority") == "HIGH" for x in ranked),
        "medium_priority": sum(x.get("priority") == "MEDIUM" for x in ranked),
        "low_priority": sum(x.get("priority") == "LOW" for x in ranked),
        "offer_ready": sum(x.get("status") == "OFFER_READY" for x in ranked),
    }
