from marketplace.opportunity_queue import add_to_queue, find_duplicate, opportunity_key, prepare_opportunity, queue_metrics, rank_queue, transition


def base_item():
    return {
        "id": "opp-1",
        "platform": "mostaql",
        "title": "مراجعة عقد شركة",
        "description": "مطلوب محامي لمراجعة عقد شركة وتحديد المخاطر واقتراح التعديلات القانونية المناسبة",
        "match_score": 85,
        "suggested_price_egp": 1500,
        "suggested_days": 2,
        "status": "NEW",
    }


def test_dedupe_key_is_stable():
    a = opportunity_key("mostaql", "  مراجعة عقد شركة ", "نص المشروع")
    b = opportunity_key("MOSTAQL", "مراجعة   عقد شركة", "نص   المشروع")
    assert a == b


def test_add_to_queue_is_idempotent():
    state = {"opportunities": []}
    first, created = add_to_queue(state, base_item(), "2026-09-06T12:00:00+00:00")
    assert created is True
    duplicate = dict(base_item(), id="opp-2")
    second, created_again = add_to_queue(state, duplicate, "2026-09-06T12:01:00+00:00")
    assert created_again is False
    assert second["id"] == first["id"]
    assert len(state["opportunities"]) == 1
    assert find_duplicate(state, "mostaql", first["title"], first["description"])["id"] == first["id"]


def test_prepare_adds_probability_and_expected_value():
    item = base_item()
    prepare_opportunity(item)
    assert 0 < item["win_probability"] <= 0.75
    assert item["expected_value_egp"] > 0
    assert item["priority"] in {"HIGH", "MEDIUM", "LOW"}


def test_lifecycle_requires_safe_order():
    item = base_item()
    transition(item, "OFFER_READY", "2026-09-06T12:00:00+00:00")
    transition(item, "READY_FOR_REVIEW", "2026-09-06T12:01:00+00:00")
    transition(item, "APPROVED", "2026-09-06T12:02:00+00:00")
    transition(item, "SUBMITTED", "2026-09-06T12:03:00+00:00")
    transition(item, "WON", "2026-09-06T12:04:00+00:00")
    assert item["status"] == "WON"
    assert item["submitted_at"] == "2026-09-06T12:03:00+00:00"
    assert item["closed_at"] == "2026-09-06T12:04:00+00:00"


def test_invalid_lifecycle_transition_fails():
    item = base_item()
    try:
        transition(item, "SUBMITTED", "2026-09-06T12:00:00+00:00")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid transition must fail")


def test_queue_rank_and_metrics():
    low = dict(base_item(), id="opp-low", match_score=30, suggested_price_egp=1000)
    high = dict(base_item(), id="opp-high", match_score=95, suggested_price_egp=3000)
    state = {"opportunities": [low, high]}
    ranked = rank_queue(state)
    assert ranked[0]["id"] == "opp-high"
    metrics = queue_metrics(state)
    assert metrics["total"] == 2
    assert metrics["expected_value_egp"] > 0


def test_submitted_opportunity_remains_in_expected_open_value():
    item = base_item()
    state = {"opportunities": [item]}
    transition(item, "OFFER_READY", "2026-09-06T12:00:00+00:00")
    transition(item, "READY_FOR_REVIEW", "2026-09-06T12:01:00+00:00")
    transition(item, "APPROVED", "2026-09-06T12:02:00+00:00")
    transition(item, "SUBMITTED", "2026-09-06T12:03:00+00:00")
    metrics = queue_metrics(state)
    assert metrics["submitted"] == 1
    assert metrics["expected_value_egp"] > 0
