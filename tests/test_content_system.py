from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from content_system import (
    build_content_tree,
    classify_feedback,
    choose_experiment,
    service_mapping,
    winner_score,
    winner_tier,
)


def test_content_tree_has_twelve_derivatives():
    tree = build_content_tree("الفصل التعسفي", "حالة واقعية", "EDUCATIONAL", "Facebook")
    assert len(tree) == 12
    assert tree[0]["asset_type"] == "POST"
    assert len({item["lineage_id"] for item in tree}) == 12


def test_service_mapping_is_business_aware():
    service, intent, cta = service_mapping("مراجعة عقد عمل قبل التوقيع")
    assert service == "مراجعة وصياغة العقود"
    assert intent == "HIGH_INTENT"
    assert cta


def test_experiment_assignment_is_deterministic():
    a = choose_experiment("إيصال الأمانة", "حالة واقعية")
    b = choose_experiment("إيصال الأمانة", "حالة واقعية")
    assert a == b
    assert a[0].startswith("EXP-")


def test_feedback_classifier_creates_content_signal():
    intent, sentiment, signal = classify_feedback("عندي نفس المشكلة، أعمل إيه؟")
    assert intent == "HOW_TO"
    assert sentiment == "NEUTRAL"
    assert signal


def test_winner_score_and_tiers_are_monotonic():
    low = winner_score({"reach": 1}, {"reach": 10})
    high = winner_score({"reach": 30}, {"reach": 10})
    assert high > low
    assert winner_tier(85) == "S"
    assert winner_tier(65) == "A"
    assert winner_tier(45) == "B"
    assert winner_tier(20) == "C"
