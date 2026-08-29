from __future__ import annotations

from collections import Counter

from recycler_rules import normalize_topic


def select_next_brief(topic_pool, used_topics, used_bases):
    """Choose the next exact brief using balanced category/core-topic rotation.

    Publication is never blocked: if no preferred candidate exists, the caller
    can still use any unused brief or its existing fallback.
    """
    used = {normalize_topic(value) for value in (used_topics or set()) if str(value).strip()}
    bases = {str(value).strip().casefold() for value in (used_bases or set()) if str(value).strip()}

    available = [
        brief for brief in topic_pool
        if normalize_topic(brief["topic"]) not in used
    ]
    if not available:
        return None

    category_usage = Counter()
    for brief in topic_pool:
        if normalize_topic(brief["topic"]) in used:
            category_usage[brief.get("category", "")] += 1

    # Prefer categories used least, then a fresh core topic, then deterministic
    # bank order. This avoids a single legal branch dominating the feed while
    # preserving reproducibility and the full 500-brief pool.
    available.sort(
        key=lambda brief: (
            category_usage[brief.get("category", "")],
            0 if brief["topic"].strip().casefold() not in bases else 1,
            normalize_topic(brief["topic"]),
            brief.get("angle", ""),
        )
    )
    return available[0]
