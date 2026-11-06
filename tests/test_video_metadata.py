from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from video_metadata import build_video_description


def test_facebook_description_uses_topic_and_approved_content_and_article_link():
    result = build_video_description(
        topic="مستحقات العامل عند إنهاء الخدمة",
        post="يجب مراجعة عقد العمل ومدة الخدمة والمستندات قبل تحديد المستحقات.",
        script="قبل إنهاء الخدمة، راجع عقد العمل ومدة الخدمة والمستندات لتحديد المستحقات.",
        article_url="https://askmahmoudkhyrat.blogspot.com/2026/11/work-rights.html",
        platform="facebook",
    )
    assert "مستحقات العامل عند إنهاء الخدمة" in result
    assert "قبل إنهاء الخدمة" in result
    assert "https://askmahmoudkhyrat.blogspot.com/2026/11/work-rights.html" in result
    assert "https://wa.me/201022718375" in result


def test_youtube_description_adds_relevant_topic_tags():
    result = build_video_description(
        topic="حقوق العامل ومنازعات العمل",
        post="راجع عقد العمل والمستندات.",
        script="راجع عقد العمل والمستندات قبل اتخاذ الإجراء.",
        platform="youtube",
    )
    assert "#حقوق_العمال" in result
    assert "#اسأل_محمود" in result


def test_description_does_not_insert_invalid_or_unrelated_article_url():
    result = build_video_description(
        topic="نزاع تجاري بين شركتين",
        post="راجع شروط العقد.",
        script="راجع شروط العقد والمراسلات.",
        article_url="https://example.com/unrelated",
        platform="facebook",
    )
    assert "example.com" not in result


def test_description_requires_actual_content():
    with pytest.raises(ValueError, match="without approved topic content"):
        build_video_description(topic="موضوع قانوني", post="", script="", platform="youtube")
