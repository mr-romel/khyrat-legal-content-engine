from marketplace.revenue import analytics, record_outcome


def test_record_won_revenue():
    item = {"lifecycle": "SUBMITTED", "status": "SUBMITTED"}
    record_outcome(item, "WON", "2026-09-06T15:00:00", 3500)
    assert item["actual_revenue_egp"] == 3500
    assert item["lifecycle"] == "WON"


def test_analytics_target_and_conversion():
    state = {"opportunities": [
        {"lifecycle": "WON", "actual_revenue_egp": 5000, "platform": "mostaql", "service_title": "مراجعة العقود"},
        {"lifecycle": "LOST", "platform": "mostaql", "service_title": "مراجعة العقود"},
        {"lifecycle": "SUBMITTED", "expected_value_egp": 2000, "platform": "mostaql"},
    ]}
    a = analytics(state)
    assert a["revenue_egp"] == 5000
    assert a["remaining_to_target_egp"] == 15000
    assert a["conversion_pct"] == 50.0
    assert a["expected_open_egp"] == 2000


def test_negative_revenue_rejected():
    try:
        record_outcome({}, "WON", "now", -1)
        assert False
    except ValueError:
        pass
