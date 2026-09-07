from datetime import datetime, timezone

from marketplace.notifications import build_notifications, notification_metrics


def test_notifications_are_local_operator_tasks():
    now = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    state = {"opportunities": [{"id": "opp-1", "title": "صياغة عقد", "lifecycle": "APPROVED", "match_score": 90}]}
    items = build_notifications(state, now)
    assert any(x["type"] == "SUBMIT" for x in items)
    metrics = notification_metrics(state, now)
    assert metrics["total"] >= 1
