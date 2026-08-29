from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def test_next_brief_avoids_immediate_category_and_angle_repetition():
    from monthly_recycler import _select_next_brief

    pool = [
        {"topic": "موضوع أ", "category": "القانون الجنائي", "angle": "زاوية 1"},
        {"topic": "موضوع ب", "category": "القانون الجنائي", "angle": "زاوية 2"},
        {"topic": "موضوع ج", "category": "قانون الأسرة", "angle": "زاوية 1"},
    ]
    chosen = _select_next_brief(
        pool,
        used_topics=set(),
        used_bases=set(),
        recent_signature=("موضوع سابق", "القانون الجنائي", "زاوية 1"),
    )
    assert chosen["topic"] == "موضوع ج"


def test_next_brief_never_reuses_published_base_topic_before_cycle_reset():
    from monthly_recycler import _select_next_brief

    pool = [
        {"topic": "موضوع أ", "category": "القانون الجنائي", "angle": "زاوية 1"},
        {"topic": "موضوع ب", "category": "قانون الأسرة", "angle": "زاوية 2"},
    ]
    chosen = _select_next_brief(pool, {"موضوع أ"}, {"موضوع أ"}, ("", "", ""))
    assert chosen["topic"] == "موضوع ب"
