from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from blogger_publisher import normalize_blogger_labels


def test_blogger_labels_stay_under_combined_character_limit():
    source = ["قانون مصر", "اسأل محمود", *[f"موضوع قانوني طويل رقم {i} مع كلمات إضافية" for i in range(20)]]
    labels = normalize_blogger_labels(source)
    assert labels
    assert len(labels) <= 10
    assert len(", ".join(labels)) <= 180
    assert len({label.casefold() for label in labels}) == len(labels)


def test_blogger_labels_remove_commas_and_newlines():
    labels = normalize_blogger_labels(["عقد, عمل\nشركات", "عقد, عمل شركات"])
    assert labels == ["عقد عمل شركات"]
