from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher


def _norm(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _angle(topic: str, row: dict[str, str]) -> str:
    explicit = str(row.get("زاوية المحتوى", "") or row.get("ملاحظات", "")).strip()
    if explicit:
        return explicit
    marker = "زاوية جديدة:"
    if marker in topic:
        return topic.split(marker, 1)[1].strip()
    return ""


def choose_due_row(candidates: list[tuple[int, dict[str, str]]], history: list[dict[str, str]]) -> tuple[int, dict[str, str]] | None:
    """Prefer unseen topics and underused categories/angles; never raise for scoring issues."""
    if not candidates:
        return None
    topic_counts = Counter(_norm(r.get("الموضوع", "")) for r in history if _norm(r.get("الموضوع", "")))
    category_counts = Counter(str(r.get("الهدف", "") or r.get("Pillar", "") or r.get("التصنيف", "")).strip() for r in history)
    angle_counts = Counter(_norm(_angle(str(r.get("الموضوع", "")), r)) for r in history if _angle(str(r.get("الموضوع", "")), r))

    def score(item: tuple[int, dict[str, str]]) -> tuple[float, int]:
        index, row = item
        topic = _norm(row.get("الموضوع", ""))
        category = str(row.get("التصنيف", "") or row.get("Pillar", "") or row.get("الهدف", "")).strip()
        angle = _norm(_angle(topic, row))
        topic_penalty = topic_counts.get(topic, 0) * 100.0
        category_bonus = 10.0 / (1 + category_counts.get(category, 0)) if category else 0.0
        angle_bonus = 8.0 / (1 + angle_counts.get(angle, 0)) if angle else 0.0
        return (-topic_penalty + category_bonus + angle_bonus, -index)

    return max(candidates, key=score)
