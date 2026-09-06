from __future__ import annotations

from datetime import datetime, timezone

from marketplace.daily_ops import build_daily_plan, task_counts


def test_daily_plan_prioritizes_due_followup_and_approved_submission():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    state = {
        "opportunities": [
            {
                "id": "opp-due",
                "platform": "mostaql",
                "title": "متابعة عقد شركة",
                "description": "مطلوب محامي لمراجعة عقد شركة",
                "lifecycle": "SUBMITTED",
                "status": "SUBMITTED",
                "updated_at": "2026-09-01T12:00:00+00:00",
                "created_at": "2026-09-01T12:00:00+00:00",
                "offer": "عرض المتابعة",
            },
            {
                "id": "opp-approved",
                "platform": "mostaql",
                "title": "صياغة عقد شراكة",
                "description": "مطلوب صياغة عقد شراكة",
                "lifecycle": "APPROVED",
                "status": "APPROVED",
                "updated_at": "2026-09-05T12:00:00+00:00",
                "created_at": "2026-09-05T12:00:00+00:00",
                "offer": "عرض جاهز",
            },
            {
                "id": "opp-new",
                "platform": "mostaql",
                "title": "مراجعة اتفاقية",
                "description": "مطلوب مراجعة اتفاقية تجارية",
                "lifecycle": "OFFER_READY",
                "status": "OFFER_READY",
                "updated_at": "2026-09-06T10:00:00+00:00",
                "created_at": "2026-09-06T10:00:00+00:00",
                "offer": "عرض مراجعة",
            },
        ],
        "services": [],
        "portfolio": [],
        "activity": [],
    }
    plan = build_daily_plan(state, now)
    assert [x["type"] for x in plan["tasks"][:3]] == ["FOLLOW_UP", "SUBMIT", "REVIEW"]
    assert task_counts(plan) == {"FOLLOW_UP": 1, "SUBMIT": 1, "REVIEW": 1}


def test_daily_plan_expires_old_open_opportunity():
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    state = {
        "opportunities": [{
            "id": "opp-old",
            "platform": "mostaql",
            "title": "مراجعة عقد قديم",
            "description": "مطلوب مراجعة عقد",
            "lifecycle": "OFFER_READY",
            "status": "OFFER_READY",
            "updated_at": "2026-09-01T12:00:00+00:00",
            "created_at": "2026-09-01T12:00:00+00:00",
        }],
        "services": [],
        "portfolio": [],
        "activity": [],
    }
    plan = build_daily_plan(state, now, stale_days=14)
    assert plan["expired_count"] == 1
    assert state["opportunities"][0]["lifecycle"] == "EXPIRED"
    assert plan["tasks"] == []
