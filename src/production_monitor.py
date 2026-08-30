from __future__ import annotations

from collections import Counter
from datetime import datetime


def summarize_publications(rows: list[dict[str, str]], recent_limit: int = 20) -> dict[str, object]:
    published = [r for r in rows if str(r.get("الحالة", "")).strip().upper() == "PUBLISHED"]
    recent = published[-recent_limit:]

    categories = Counter(str(r.get("التصنيف", "") or r.get("Pillar", "") or r.get("الهدف", "")).strip() for r in recent)
    angles = Counter(str(r.get("زاوية المحتوى", "")).strip() for r in recent if str(r.get("زاوية المحتوى", "")).strip())
    topics = Counter(str(r.get("الموضوع", "")).strip() for r in recent if str(r.get("الموضوع", "")).strip())

    duplicate_topics = {topic: count for topic, count in topics.items() if count > 1}
    return {
        "checked_at": datetime.now().astimezone().isoformat(),
        "published_total": len(published),
        "recent_checked": len(recent),
        "category_counts": dict(categories),
        "angle_counts": dict(angles),
        "duplicate_recent_topics": duplicate_topics,
        "recent_topic_count": len(topics),
        "healthy_diversity": not duplicate_topics,
    }


def format_telegram_monitor(summary: dict[str, object]) -> str:
    duplicate = summary.get("duplicate_recent_topics") or {}
    status = "OK" if summary.get("healthy_diversity") else "REVIEW"
    return (
        f"Content monitor: {status}\n"
        f"Published total: {summary.get('published_total', 0)} | "
        f"Recent checked: {summary.get('recent_checked', 0)} | "
        f"Recent unique topics: {summary.get('recent_topic_count', 0)}\n"
        f"Recent duplicate topics: {len(duplicate)}"
    )
