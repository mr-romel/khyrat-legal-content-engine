from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reel_pipeline import post_visual_terms, topic_visual_terms


def test_secret_disclosure_visuals_are_specific_to_digital_threat_evidence():
    terms = post_visual_terms(
        "التهديد بإفشاء الأسرار عبر رسائل خاصة، مع ضرورة حفظ الرسائل وتوقيتاتها وإثبات نسبتها.",
        "التهديد بإفشاء الأسرار",
    )
    joined = " ".join(terms).lower()
    assert len(terms) >= 8
    assert "threatening" in joined
    assert "smartphone" in joined
    assert "timestamp" in joined or "date and time" in joined
    assert "confidential" in joined
    assert "courtroom" not in joined
    assert "gavel" not in joined


def test_secret_disclosure_topic_visual_fallback_is_not_generic_legal_stock():
    terms = topic_visual_terms("التهديد بإفشاء الأسرار")
    assert len(terms) >= 8
    assert any("threatening" in item for item in terms)
    assert any("confidential" in item for item in terms)
    assert any("smartphone" in item for item in terms)
