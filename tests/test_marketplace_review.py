import pytest

from marketplace.review import transition
from marketplace.adapters import KhamsatAdapter, MostaqlAdapter


def test_draft_can_be_sent_to_review():
    item = {"id": "x", "status": "DRAFT"}
    result = transition(item, "READY_FOR_REVIEW")
    assert result.new_status == "READY_FOR_REVIEW"
    assert item["reviewed_at"]


def test_review_can_approve_or_reject():
    item = {"id": "x", "status": "READY_FOR_REVIEW"}
    transition(item, "APPROVED")
    assert item["status"] == "APPROVED"


def test_invalid_transition_is_blocked():
    item = {"id": "x", "status": "DRAFT"}
    with pytest.raises(ValueError):
        transition(item, "PUBLISHED")


def test_platforms_are_manual_in_mvp():
    assert KhamsatAdapter().capabilities().requires_manual_approval
    assert MostaqlAdapter().capabilities().requires_manual_approval
    assert not KhamsatAdapter().capabilities().can_publish_automatically
    assert not MostaqlAdapter().capabilities().can_publish_automatically


def test_mostaql_prepares_offer_without_submitting():
    payload = MostaqlAdapter().prepare_offer({"id": "opp-1", "title": "مراجعة عقد"})
    assert payload["action"] == "SUBMIT_OFFER"
    assert payload["payload"]["id"] == "opp-1"
