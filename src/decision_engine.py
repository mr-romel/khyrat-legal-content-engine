from __future__ import annotations

from collections import Counter


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


def choose_due_row(candidates: list[tuple[int, dict[str, str]]], history: list[dict[str, str]]) -> tuple[int, dict[str, str]] | None:
    """Prefer unseen base topics and underused categories/angles; never block publication."""
    if not candidates:
        return None

    base_counts = Counter(_base_topic(r.get("الموضوع", "")) for r in history if _base_topic(r.get("الموضوع", "")))
    category_counts = Counter(_category(r) for r in history if _category(r))
    angle_counts = Counter(_norm(_angle(str(r.get("الموضوع", "")), r)) for r in history if _angle(str(r.get("الموضوع", "")), r))

    def score(item: tuple[int, dict[str, str]]) -> tuple[float, float, float, int]:
        index, row = item
        base = _base_topic(row.get("الموضوع", ""))
        category = _category(row)
        angle = _norm(_angle(str(row.get("الموضوع", "")), row))

        # Base-topic reuse is the strongest negative signal. Category/angle balancing
        # is secondary, so a fresh subject beats a familiar subject with a new angle.
        topic_penalty = base_counts.get(base, 0) * 1000.0
        category_bonus = 20.0 / (1 + category_counts.get(category, 0)) if category else 0.0
        angle_bonus = 15.0 / (1 + angle_counts.get(angle, 0)) if angle else 0.0
        return (-topic_penalty + category_bonus + angle_bonus, category_bonus, angle_bonus, -index)

    return max(candidates, key=score)
