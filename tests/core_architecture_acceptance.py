from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def test_similarity_engine_exposes_reusable_api():
    from content_similarity import highest_similarity
    score, match = highest_similarity("same legal topic", ["same legal topic"], 0.72)
    assert score >= 0.99
    assert match == "same legal topic"


def test_post_bank_tracks_angle_history():
    from post_bank import build_previous_context
    context = build_previous_context([{"الموضوع": "موضوع أ", "زاوية المحتوى": "زاوية أ", "المحتوى": "نص"}])
    assert "زاوية أ" in context


def test_decision_engine_prefers_less_used_topic():
    from decision_engine import choose_due_row
    candidates = [(2, {"الموضوع": "موضوع قديم", "التصنيف": "جنائي"}), (3, {"الموضوع": "موضوع جديد", "التصنيف": "إداري"})]
    history = [{"الموضوع": "موضوع قديم", "التصنيف": "جنائي"}]
    selected = choose_due_row(candidates, history)
    assert selected is not None
    assert selected[0] == 3


def test_continuous_publishing_policy_is_not_blocked_by_similarity():
    source = (SRC / "run_main.py").read_text(encoding="utf-8")
    assert "publishing original as required by continuous-publishing policy" in source
    assert "Similarity gate: REWRITE requested" in source


def test_core_pipeline_modules_exist():
    for name in ["main.py", "run_main.py", "content_similarity.py", "monthly_recycler.py", "post_bank.py", "telegram_publication.py", "analytics.py", "decision_engine.py"]:
        assert (SRC / name).is_file(), name
