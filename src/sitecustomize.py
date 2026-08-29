"""Runtime compatibility patch for the topic-rotation invariant.

The expanded bank intentionally contains 16 briefs per subject (one per angle),
so topic names are expected to repeat across angle-specific briefs.  The legacy
invariant incorrectly treated repeated topic names as duplicated briefs.
"""

try:
    import hashlib
    import recycler_rules as _rules

    def _patched_topic_pool_for_month(current_key, used_topics):
        used = {str(value).strip().casefold() for value in (used_topics or set()) if str(value).strip()}
        available = [
            item for item in _rules.EXPANDED_TOPIC_BANK
            if _rules.normalize_topic(item["topic"]) not in used
        ]
        if not available:
            available = list(_rules.EXPANDED_TOPIC_BANK)

        def rank(item):
            return hashlib.sha256(
                f"{current_key}|{item['category']}|{item['topic']}|{item['angle']}".encode("utf-8")
            ).hexdigest()

        buckets = {category: [] for category in _rules.CATEGORY_ORDER}
        extras = []
        for item in available:
            (buckets[item["category"]] if item["category"] in buckets else extras).append(item)
        for bucket in buckets.values():
            bucket.sort(key=rank)
        extras.sort(key=rank)

        start = int(hashlib.sha256(current_key.encode("utf-8")).hexdigest()[:8], 16) % len(_rules.CATEGORY_ORDER)
        ordered_categories = [
            _rules.CATEGORY_ORDER[(start + i) % len(_rules.CATEGORY_ORDER)]
            for i in range(len(_rules.CATEGORY_ORDER))
        ]

        result = []
        while any(buckets[c] for c in ordered_categories):
            for category in ordered_categories:
                if buckets[category]:
                    result.append(buckets[category].pop(0))
        result.extend(extras)

        brief_keys = {
            (
                _rules.normalize_topic(item["topic"]),
                item.get("category", "").strip().casefold(),
                item.get("angle", "").strip().casefold(),
            )
            for item in result
        }
        if len(result) != len(available) or len(brief_keys) != len(available):
            raise RuntimeError("Topic rotation invariant failed: briefs were lost or duplicated")
        return result

    _rules.topic_pool_for_month = _patched_topic_pool_for_month
    _rules._topic_pool_for_month = _patched_topic_pool_for_month
except Exception:
    # Never prevent normal application startup because of this compatibility shim.
    pass
