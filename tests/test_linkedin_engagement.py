from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from linkedin_engagement_worker import parse_dt, select_due


def test_parse_dt_cairo():
    value = parse_dt("2026-09-19T15:00:00+03:00")
    assert value is not None
    assert value.tzinfo is not None
    assert value.hour == 15


def test_select_due_ignores_published_and_future():
    rows = [
        {"status": "PENDING", "scheduled_at": "2026-09-19T14:00:00+03:00"},
        {"status": "PUBLISHED", "scheduled_at": "2026-09-19T14:00:00+03:00"},
        {"status": "RETRY", "scheduled_at": "2026-09-19T16:00:00+03:00"},
    ]
    current = datetime(2026, 9, 19, 15, 0, tzinfo=ZoneInfo("Africa/Cairo"))
    due = select_due(rows, current)
    assert len(due) == 1
    assert due[0]["status"] == "PENDING"


def test_select_due_includes_permission_recheck():
    rows = [{"status": "BLOCKED_PERMISSION", "scheduled_at": "2026-09-19T14:00:00+03:00"}]
    current = datetime(2026, 9, 19, 15, 0, tzinfo=ZoneInfo("Africa/Cairo"))
    assert len(select_due(rows, current)) == 1
