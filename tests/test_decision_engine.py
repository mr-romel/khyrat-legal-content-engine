from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_engine import choose_due_row


def _row(topic, publish_time, status="READY"):
    return {
        "الموضوع": topic,
        "تاريخ النشر": "2026-09-25",
        "ساعة النشر": publish_time,
        "الحالة": status,
        "التصنيف": "القانون الجنائي",
        "ملاحظات": "",
    }


def test_newer_due_slot_beats_stale_failed_row():
    candidates = [
        (2, _row("موضوع قديم", "15:00", "FAILED")),
        (3, _row("موضوع الساعة", "17:00", "READY")),
    ]
    selected = choose_due_row(candidates, history=[])
    assert selected is not None
    assert selected[0] == 3


def test_content_diversity_still_breaks_ties_for_same_time():
    candidates = [
        (2, _row("موضوع مستخدم", "17:00")),
        (3, _row("موضوع جديد", "17:00")),
    ]
    history = [{"الموضوع": "موضوع مستخدم", "التصنيف": "القانون الجنائي"}]
    selected = choose_due_row(candidates, history=history)
    assert selected is not None
    assert selected[0] == 3
