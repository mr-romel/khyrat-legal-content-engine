from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_feedback_loop_prefers_fresh_base_topic():
    from decision_engine import choose_due_row

    history = [
        {"الموضوع": "توزيع الأرباح — زاوية جديدة: الوقاية", "التصنيف": "قانون الشركات والاستثمار", "زاوية المحتوى": "الوقاية"},
        {"الموضوع": "توزيع الأرباح — زاوية جديدة: خطأ شائع", "التصنيف": "قانون الشركات والاستثمار", "زاوية المحتوى": "خطأ شائع"},
    ]
    candidates = [
        (2, {"الموضوع": "توزيع الأرباح — زاوية جديدة: حالة واقعية", "التصنيف": "قانون الشركات والاستثمار", "زاوية المحتوى": "حالة واقعية"}),
        (3, {"الموضوع": "إدارة الشركة — زاوية جديدة: الوقاية", "التصنيف": "قانون الشركات والاستثمار", "زاوية المحتوى": "الوقاية"}),
    ]
    selected = choose_due_row(candidates, history)
    assert selected[1]["الموضوع"].startswith("إدارة الشركة")


def test_similarity_rewrite_contract_is_present():
    import inspect
    import run_main
    source = inspect.getsource(run_main._capture_editorial_assets)
    assert "highest_similarity" in source
    assert "rewrite" in source.lower()
    assert "publishing original" in source.lower()


def test_monitoring_reports_duplicate_topics():
    from production_monitor import summarize_publications

    rows = [
        {"الحالة": "PUBLISHED", "الموضوع": "أ", "التصنيف": "جنائي"},
        {"الحالة": "PUBLISHED", "الموضوع": "أ", "التصنيف": "جنائي"},
        {"الحالة": "PUBLISHED", "الموضوع": "ب", "التصنيف": "أسرة"},
    ]
    summary = summarize_publications(rows, recent_limit=20)
    assert summary["healthy_diversity"] is False
    assert summary["duplicate_recent_topics"] == {"أ": 2}


if __name__ == "__main__":
    test_feedback_loop_prefers_fresh_base_topic()
    test_similarity_rewrite_contract_is_present()
    test_monitoring_reports_duplicate_topics()
    print("Final architecture acceptance tests: OK")
