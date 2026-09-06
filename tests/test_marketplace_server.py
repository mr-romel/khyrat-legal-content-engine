from __future__ import annotations

from marketplace.server import handle_action


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
