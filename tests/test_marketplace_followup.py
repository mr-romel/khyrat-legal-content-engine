from datetime import datetime, timedelta, timezone

from marketplace.followup import due_followups, expire_stale, followup_metrics, next_followup


def test_submitted_followup_is_two_days_after_update():
    now = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
    item = {"lifecycle": "SUBMITTED", "updated_at": "2026-09-06T10:00:00+00:00"}
    assert next_followup(item, now) == "2026-09-08T10:00:00+00:00"


def test_due_followups_are_sorted_and_terminal_items_are_ignored():
    now = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
    state = {"opportunities": [
        {"id": "opp-2", "lifecycle": "SUBMITTED", "updated_at": "2026-09-01T10:00:00+00:00"},
        {"id": "opp-1", "lifecycle": "READY_FOR_REVIEW", "updated_at": "2026-09-04T10:00:00+00:00"},
        {"id": "opp-3", "lifecycle": "WON", "updated_at": "2026-08-01T10:00:00+00:00"},
    ]}
    due = due_followups(state, now)
    assert [x["id"] for x in due] == ["opp-2", "opp-1"]
    assert followup_metrics(state, now) == {"due": 2, "submitted_due": 1, "review_due": 1}


def test_expire_stale_marks_only_old_open_opportunities():
    now = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
    state = {"opportunities": [
        {"id": "old", "lifecycle": "NEW", "updated_at": (now - timedelta(days=15)).isoformat()},
        {"id": "fresh", "lifecycle": "SUBMITTED", "updated_at": (now - timedelta(days=2)).isoformat()},
        {"id": "won", "lifecycle": "WON", "updated_at": (now - timedelta(days=30)).isoformat()},
    ]}
    assert expire_stale(state, now, stale_days=14) == ["old"]
    assert state["opportunities"][0]["lifecycle"] == "EXPIRED"
    assert state["opportunities"][1]["lifecycle"] == "SUBMITTED"
