from monthly_recycler import _topic_pool_for_month

pool = _topic_pool_for_month("2026-08", set())
assert len(pool) == 500, f"expected 500 briefs, got {len(pool)}"
assert len({item["topic"] for item in pool}) == 500, "topic titles must remain unique"

first_month = [item["topic"] for item in _topic_pool_for_month("2026-08", set())[:30]]
next_month = [item["topic"] for item in _topic_pool_for_month("2026-09", set())[:30]]
assert first_month != next_month, "monthly rotation must change the leading sequence"

print("500-topic monthly rotation/diversification check: OK")
