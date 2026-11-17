import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pilot import build_script, choose_next_row, _parse_schedule, render_slide

CAIRO = ZoneInfo("Africa/Cairo")


def test_selects_nearest_future_scheduled_topic():
    now = datetime(2026, 10, 16, 9, 0, tzinfo=CAIRO)
    rows = [
        {"ID": "later", "الموضوع": "موضوع لاحق", "تاريخ النشر": "2026-10-18", "ساعة النشر": "09:00", "الحالة": "READY"},
        {"ID": "next", "الموضوع": "الموضوع التالي", "تاريخ النشر": "2026-10-16", "ساعة النشر": "11:30", "الحالة": "READY"},
    ]
    row, scheduled = choose_next_row(rows, now=now)
    assert row["ID"] == "next"
    assert scheduled.hour == 11 and scheduled.minute == 30


def test_refuses_to_guess_if_no_future_schedule():
    rows = [{"الموضوع": "قديم", "تاريخ النشر": "2026-10-15", "ساعة النشر": "09:00"}]
    try:
        choose_next_row(rows, now=datetime(2026, 10, 16, 9, 0, tzinfo=CAIRO))
    except RuntimeError as exc:
        assert "Refusing to guess" in str(exc)
    else:
        raise AssertionError("Expected a refusal when no future scheduled row exists")


def test_script_keeps_topic_and_disclaimer():
    script = build_script(
        {"الموضوع": "مراجعة عقد العمل", "المحتوى": "راجع مدة العقد والأجر وساعات العمل والإجازات قبل التوقيع."}
    )
    assert script["topic"] == "مراجعة عقد العمل"
    assert script["publishing_enabled"] is False
    assert "مش بديل" in script["narration"]


def test_slide_is_portrait_and_renderable(tmp_path):
    target = tmp_path / "slide.png"
    render_slide(target, 0, "مراجعة عقد العمل", "راجع الأجر ومدة العقد قبل التوقيع.", 5)
    from PIL import Image
    with Image.open(target) as image:
        assert image.size == (1080, 1920)
