from marketplace.opportunity_engine import queue_metrics, rank_opportunity, rank_queue


def test_legal_opportunity_gets_high_priority():
    item = {
        "title": "مطلوب محامي لمراجعة عقد شركة",
        "description": "أحتاج مراجعة عقد تجاري وتحديد المخاطر والالتزامات والاقتراحات على البنود قبل التوقيع." * 2,
        "match_score": 90,
        "status": "OFFER_READY",
    }
    ranked = rank_opportunity(item)
    assert ranked["acquisition_score"] >= 75
    assert ranked["priority"] == "HIGH"


def test_queue_is_sorted_descending():
    state = {"opportunities": [
        {"title": "تصميم شعار", "description": "شعار", "match_score": 5},
        {"title": "مراجعة عقد شركة", "description": "محامي مراجعة عقد شركة", "match_score": 85},
    ]}
    ranked = rank_queue(state)
    assert ranked[0]["match_score"] > ranked[1]["match_score"]


def test_queue_metrics():
    state = {"opportunities": [
        {"title": "محامي مراجعة عقد", "description": "شركة وعقد" * 40, "match_score": 90, "status": "OFFER_READY"},
        {"title": "تصميم", "description": "تصميم" * 40, "match_score": 0, "status": "DRAFT"},
    ]}
    metrics = queue_metrics(state)
    assert metrics["high_priority"] >= 1
    assert metrics["offer_ready"] == 1
