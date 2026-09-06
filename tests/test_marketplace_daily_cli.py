from __future__ import annotations

import json
from datetime import datetime, timezone

import marketplace_daily


def test_daily_cli_writes_plan(tmp_path, monkeypatch, capsys):
    state = {
        "services": [],
        "portfolio": [],
        "opportunities": [{
            "id": "opp-1",
            "platform": "mostaql",
            "title": "مراجعة عقد شركة",
            "description": "مطلوب محامي لمراجعة عقد شركة وتحديد المخاطر القانونية",
            "match_score": 90,
            "suggested_price_egp": 1500,
            "suggested_days": 2,
            "status": "APPROVED",
            "lifecycle": "APPROVED",
            "created_at": "2026-09-06T10:00:00+00:00",
            "updated_at": "2026-09-06T10:00:00+00:00",
            "offer": "أراجع العقد وأحدد المخاطر والتعديلات المقترحة.",
        }],
        "activity": [],
    }
    monkeypatch.setattr(marketplace_daily, "load_state", lambda: state)
    monkeypatch.setattr(marketplace_daily, "save_state", lambda s: None)
    out = tmp_path / "daily_plan.json"
    monkeypatch.setattr(
        "sys.argv",
        ["marketplace_daily", "--output", str(out)],
    )

    assert marketplace_daily.main() == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["tasks"][0]["type"] == "SUBMIT"
    assert payload["tasks"][0]["id"] == "opp-1"
    assert "عروض جاهزة للتقديم: 1" in capsys.readouterr().out
