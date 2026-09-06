from marketplace.revenue import analytics, record_outcome


def test_record_won_revenue():
    item = {"lifecycle": "SUBMITTED", "status": "SUBMITTED"}
    record_outcome(item, "WON", "2026-09-06T15:00:00", 3500)
    assert item["actual_revenue_egp"] == 3500
    assert item["lifecycle"] == "WON"


def test_analytics_target_and_conversion():
    state = {"opportunities": [
        {"lifecycle": "WON", "actual_revenue_egp": 5000, "closed_at": "2026-09-06T15:00:00", "platform": "mostaql", "service_title": "مراجعة العقود"},
        {"lifecycle": "LOST", "platform": "mostaql", "service_title": "مراجعة العقود"},
        {"lifecycle": "SUBMITTED", "expected_value_egp": 2000, "platform": "mostaql"},
    ]}
    a = analytics(state, month="2026-09")
    assert a["revenue_egp"] == 5000
    assert a["remaining_to_target_egp"] == 15000
    assert a["conversion_pct"] == 50.0
    assert a["expected_open_egp"] == 2000
    assert a["average_win_egp"] == 5000
    assert a["top_service"] == "مراجعة العقود"
    assert a["top_platform"] == "mostaql"


def test_old_revenue_not_counted_in_current_month():
    state = {"opportunities": [
        {"lifecycle": "WON", "actual_revenue_egp": 9000, "closed_at": "2026-08-31T20:00:00"},
        {"lifecycle": "WON", "actual_revenue_egp": 3000, "closed_at": "2026-09-01T10:00:00"},
    ]}
    a = analytics(state, month="2026-09")
    assert a["revenue_egp"] == 3000
    assert a["lifetime_revenue_egp"] == 12000


def test_outcome_requires_submitted():
    try:
        record_outcome({"lifecycle": "APPROVED"}, "WON", "now", 1000)
        assert False
    except ValueError:
        pass


def test_outcome_cannot_be_recorded_twice():
    item = {"lifecycle": "SUBMITTED"}
    record_outcome(item, "WON", "now", 1000)
    try:
        record_outcome(item, "LOST", "later", 0)
        assert False
    except ValueError:
        pass


def test_negative_revenue_rejected():
    try:
        record_outcome({"lifecycle": "SUBMITTED"}, "WON", "now", -1)
        assert False
    except ValueError:
        pass


def test_won_requires_amount():
    try:
        record_outcome({"lifecycle": "SUBMITTED"}, "WON", "now")
        assert False
    except ValueError:
        pass
