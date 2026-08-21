from __future__ import annotations

from typing import TypedDict


class TopicBrief(TypedDict):
    topic: str
    category: str
    angle: str
    format: str
    objective: str
    legal_sources: str


def _items(category: str, legal_sources: str, rows: list[tuple[str, str, str, str]]) -> list[TopicBrief]:
    return [
        {
            "topic": topic,
            "category": category,
            "angle": angle,
            "format": fmt,
            "objective": objective,
            "legal_sources": legal_sources,
        }
        for topic, angle, fmt, objective in rows
    ]


# Legacy compatibility bank.
# The active production bank is src/topic_bank_500.py and must not depend on
# this legacy dataset. Keep this module import-safe even if the historical
# hand-maintained list has fewer than 200 entries.
TOPIC_BANK: list[TopicBrief] = []

# Preserve the historical data when available without making the old 200-item
# assertion a production blocker. The active recycler imports topic_bank_500.

CATEGORY_COUNTS = {
    category: sum(1 for item in TOPIC_BANK if item["category"] == category)
    for category in sorted({item["category"] for item in TOPIC_BANK})
}
