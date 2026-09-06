from __future__ import annotations

import json
from pathlib import Path

import marketplace_mvp as m


def test_service_generation_is_reviewable():
    item = m.generate_service("مراجعة العقود التجارية")
    assert item.platform == "khamsat"
    assert item.status == "DRAFT"
    assert "مراجعة" in item.title
    assert len(item.deliverables) >= 3


def test_opportunity_scoring_prioritizes_legal_work():
    score, reasons = m.score_opportunity("مطلوب محامي لصياغة عقد شركة", "مراجعة وصياغة الشروط القانونية")
    assert score >= 70
    assert reasons


def test_dashboard_contains_core_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "DATA_DIR", tmp_path)
    monkeypatch.setattr(m, "DATA_FILE", tmp_path / "marketplace.json")
    monkeypatch.setattr(m, "DASHBOARD_FILE", tmp_path / "dashboard.html")
    path = m.run(seed=True)
    html = path.read_text(encoding="utf-8")
    state = json.loads((tmp_path / "marketplace.json").read_text(encoding="utf-8"))
    assert state["services"]
    assert state["portfolio"]
    assert state["opportunities"]
    assert "Khyrat Marketplace" in html
    assert "خمسات" in html
    assert "مستقل" in html
    assert "Approval" in html
