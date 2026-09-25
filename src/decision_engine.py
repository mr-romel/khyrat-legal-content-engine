from __future__ import annotations

from collections import Counter
from datetime import datetime

from utils import parse_date, parse_time


def _norm(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _base_topic(value: str) -> str:
    text = str(value or "").strip()
    for marker in (" — زاوية جديدة:", " - زاوية جديدة:"):
        if marker in text:
            text = text.split(marker, 1)[0].strip()
    return _norm(text)


def _angle(topic: str, row: dict[str, str]) -> str:
    explicit = str(row.get("زاوية المحتوى", "") or "").strip()
    if explicit:
        return explicit
    notes = str(row.get("ملاحظات", "") or "").strip()
    if "زاوية:" in notes:
        return notes.split("زاوية:", 1)[1].split("|", 1)[0].strip()
    marker = "زاوية جديدة:"
    if marker in topic:
        return topic.split(marker, 1)[1].strip()
    return ""


def _category(row: dict[str, str]) -> str:
    return str(row.get("التصنيف", "") or row.get("Pillar", "") or row.get("الهدف", "")).strip()


def _scheduled_at(row: dict[str, str]):
    try:
        target_date = parse_date(row.get("تاريخ النشر", ""))
        target_time = parse_time(row.get("ساعة النشر", ""))
        if target_date is None or target_time is None:
            return None
        return datetime.combine(target_date, target_time)
    except (TypeError, ValueError):
        return None


def choose_due_row(
    candidates: list[tuple[int, dict[str, str]]],
    history: list[dict[str, str]],
    current: datetime | None = None,
) -> tuple[int, dict[str, str]] | None:
    """Choose the most time-urgent due row, then apply content-diversity scoring.

    Publication timing is a hard priority. A stale failed row must never starve a
    newer scheduled slot just because its topic happens to score better on the
    diversity signals.
    """
    if not candidates:
        return None

    base_counts = Counter(_base_topic(r.get("الموضوع", "")) for r in history if _base_topic(r.get("الموضوع", "")))
    category_counts = Counter(_category(r) for r in history if _category(r))
    angle_counts = Counter(_norm(_angle(str(r.get("الموضوع", "")), r)) for r in history if _angle(str(r.get("الموضوع", "")), r))

    def score(item: tuple[int, dict[str, str]]):
        index, row = item
        scheduled_at = _scheduled_at(row)
        # Among due rows, prefer the latest scheduled slot (the one closest to
        # now). This prevents a 15:00 failure from consuming the 17:00 slot.
        # If current is unavailable, scheduled time still provides a stable
        # deterministic ordering.
        time_priority = scheduled_at.timestamp() if scheduled_at is not None else float("-inf")
        base = _base_topic(row.get("الموضوع", ""))
        category = _category(row)
        angle = _norm(_angle(str(row.get("الموضوع", "")), row))

        # Base-topic reuse is the strongest negative signal. Category/angle balancing
        # is secondary, so a fresh subject beats a familiar subject with a new angle.
        topic_penalty = base_counts.get(base, 0) * 1000.0
        category_bonus = 20.0 / (1 + category_counts.get(category, 0)) if category else 0.0
        angle_bonus = 15.0 / (1 + angle_counts.get(angle, 0)) if angle else 0.0
        return (time_priority, -topic_penalty + category_bonus + angle_bonus, category_bonus, angle_bonus, -index)

    return max(candidates, key=score)
