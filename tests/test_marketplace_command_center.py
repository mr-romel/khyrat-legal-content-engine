from datetime import datetime, timezone

from marketplace.command_center import build_command_center, next_action


def test_command_center_uses_20k_target():
    state = {"opportunities": []}
    center = build_command_center(state, month="2026-09")
    assert center["target_egp"] == 20000
    assert center["remaining_to_target_egp"] == 20000
    assert center["target_reached"] is False
    assert "20,000" in center["headline"]
    assert next_action(center)


def test_command_center_counts_wins():
    state = {"opportunities": [{"id": "1", "lifecycle": "WON", "closed_at": "2026-09-05T12:00:00+00:00", "actual_revenue_egp": 5000}]}
    center = build_command_center(state, month="2026-09")
    assert center["revenue_egp"] == 5000
    assert center["remaining_to_target_egp"] == 15000
    assert center["average_win_egp"] == 5000
    assert center["deals_needed_at_average_win"] == 3
