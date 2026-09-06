from __future__ import annotations

from marketplace.server import handle_action, render_dashboard


def test_ready_then_approve_service():
    state = {"services": [{"id": "svc-1", "status": "DRAFT"}], "opportunities": [], "activity": []}
    import marketplace.server as server
    old_load, old_save = server.load_state, server.save_state
    try:
        server.load_state = lambda: state
        server.save_state = lambda s: None
        ok, _ = handle_action({"id": "svc-1", "action": "ready"})
        assert ok and state["services"][0]["status"] == "READY_FOR_REVIEW"
        ok, _ = handle_action({"id": "svc-1", "action": "approve"})
        assert ok and state["services"][0]["status"] == "APPROVED"
    finally:
        server.load_state, server.save_state = old_load, old_save


def test_invalid_direct_approve_is_rejected():
    state = {"services": [{"id": "svc-1", "status": "DRAFT"}], "opportunities": [], "activity": []}
    import marketplace.server as server
    old_load, old_save = server.load_state, server.save_state
    try:
        server.load_state = lambda: state
        server.save_state = lambda s: None
        ok, _ = handle_action({"id": "svc-1", "action": "approve"})
        assert not ok
        assert state["services"][0]["status"] == "DRAFT"
    finally:
        server.load_state, server.save_state = old_load, old_save


def test_dashboard_shows_due_followup_and_direct_link():
    state = {
        "services": [],
        "portfolio": [],
        "opportunities": [{
            "id": "opp-1",
            "platform": "mostaql",
            "title": "مراجعة عقد شركة",
            "description": "مطلوب محامي لمراجعة عقد شركة وتحديد المخاطر واقتراح التعديلات القانونية المناسبة",
            "match_score": 85,
            "suggested_price_egp": 1500,
            "suggested_days": 2,
            "status": "SUBMITTED",
            "lifecycle": "SUBMITTED",
            "updated_at": "2026-09-01T12:00:00+00:00",
            "created_at": "2026-09-01T12:00:00+00:00",
            "source_url": "https://mostaql.com/project/123456",
            "offer": "أراجع العقد وأحدد المخاطر والبنود المقترحة للتعديل.",
        }],
        "activity": [],
    }
    html = render_dashboard(state)
    assert "مهام اليوم" in html
    assert "فتح المشروع على مستقل" in html
    assert "https://mostaql.com/project/123456" in html
    assert "موعد المتابعة" in html
    assert "تمت المتابعة" in html
    assert "نسخ العرض" in html
    assert "navigator.clipboard.writeText" in html
    assert "https://mostaql.com/project/123456" in html


def test_follow_up_updates_next_followup_and_activity():
    state = {
        "services": [],
        "opportunities": [{
            "id": "opp-1",
            "status": "SUBMITTED",
            "lifecycle": "SUBMITTED",
            "updated_at": "2026-09-01T12:00:00+00:00",
            "created_at": "2026-09-01T12:00:00+00:00",
        }],
        "activity": [],
    }
    import marketplace.server as server
    old_load, old_save, old_now = server.load_state, server.save_state, server._now
    try:
        server.load_state = lambda: state
        server.save_state = lambda s: None
        server._now = lambda: "2026-09-06T12:00:00+00:00"
        ok, message = handle_action({"id": "opp-1", "action": "follow_up"})
        assert ok
        assert message == "تم تنفيذ الإجراء"
        assert state["opportunities"][0]["updated_at"] == "2026-09-06T12:00:00+00:00"
        assert state["opportunities"][0]["next_followup_at"] == "2026-09-08T12:00:00+00:00"
        assert state["activity"][0]["message"] == "follow_up: opp-1"
    finally:
        server.load_state, server.save_state, server._now = old_load, old_save, old_now


def test_follow_up_rejected_before_submission():
    state = {
        "services": [],
        "opportunities": [{"id": "opp-1", "status": "APPROVED", "lifecycle": "APPROVED"}],
        "activity": [],
    }
    import marketplace.server as server
    old_load, old_save = server.load_state, server.save_state
    try:
        server.load_state = lambda: state
        server.save_state = lambda s: None
        ok, message = handle_action({"id": "opp-1", "action": "follow_up"})
        assert not ok
        assert "الفرص المرسلة" in message
    finally:
        server.load_state, server.save_state = old_load, old_save
