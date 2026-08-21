from __future__ import annotations

from typing import TypedDict


class TopicBrief(TypedDict):
    topic: str
    category: str
    angle: str
    format: str
    objective: str
    legal_sources: str


# Compatibility adapter only.
# Production/recycling uses src.topic_bank_500 directly.  This module remains
# import-safe for older callers and no longer contains a stale 200-topic gate.
from src.topic_bank_500 import TOPIC_BANK as TOPIC_BANK  # noqa: E402

CATEGORY_COUNTS = {
    "القانون الجنائي": 0,
    "قانون الشركات والاستثمار": 0,
    "قانون الأسرة": 0,
    "قانون العمل الجديد": 0,
    "القانون الإداري": 0,
}

for _item in TOPIC_BANK:
    _category = _item["category"]
    CATEGORY_COUNTS[_category] = CATEGORY_COUNTS.get(_category, 0) + 1

if len(TOPIC_BANK) != 500:
    raise RuntimeError(f"Active TOPIC_BANK must contain exactly 500 topics; found {len(TOPIC_BANK)}")

if any(count != 100 for count in CATEGORY_COUNTS.values()):
    raise RuntimeError(f"Active TOPIC_BANK category distribution must be 100 each; found {CATEGORY_COUNTS}")
