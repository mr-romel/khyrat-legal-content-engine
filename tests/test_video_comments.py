from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from video_comments import (
    build_video_comment_bundle,
    parse_published_comment_ids,
    valid_blogger_article_url,
)


def test_blogger_article_url_must_be_exact_blog_and_specific_post():
    assert valid_blogger_article_url("https://askmahmoudkhyrat.blogspot.com/2026/11/legal-topic.html")
    assert not valid_blogger_article_url("https://example.com/2026/11/legal-topic.html")
    assert not valid_blogger_article_url("https://askmahmoudkhyrat.blogspot.com/")
    assert not valid_blogger_article_url("http://askmahmoudkhyrat.blogspot.com/2026/11/legal-topic.html")


@pytest.mark.parametrize("platform", ["facebook", "youtube"])
def test_comment_bundle_has_three_to_five_comments_and_required_roles(platform):
    comments = build_video_comment_bundle(
        topic="إثبات ساعات العمل ومستحقات العامل",
        article_url="https://askmahmoudkhyrat.blogspot.com/2026/11/work-rights.html",
        video_id="video_123",
        platform=platform,
    )
    assert 3 <= len(comments) <= 5
    assert any("askmahmoudkhyrat.blogspot.com/2026/11/work-rights.html" in item for item in comments)
    assert comments[0].endswith("؟") and len(comments[0]) > 30
    assert len(comments[1]) > 60 and comments[1].endswith("؟") is False


def test_bundle_is_stable_for_retry_but_varies_by_video_and_platform():
    args = {
        "topic": "نزاع عمالي",
        "article_url": "https://askmahmoudkhyrat.blogspot.com/2026/11/work.html",
        "video_id": "reel_A",
    }
    first = build_video_comment_bundle(**args, platform="facebook")
    retry = build_video_comment_bundle(**args, platform="facebook")
    other_video = build_video_comment_bundle(**{**args, "video_id": "reel_B"}, platform="facebook")
    youtube = build_video_comment_bundle(**args, platform="youtube")
    assert first == retry
    assert first != other_video
    assert first != youtube


def test_comment_bundle_refuses_to_run_without_the_matching_blog_article():
    with pytest.raises(ValueError, match="topic-matched Blogger article"):
        build_video_comment_bundle(
            topic="نزاع عمالي",
            article_url="",
            video_id="reel_A",
            platform="facebook",
        )


def test_comment_ids_parser_is_safe():
    assert parse_published_comment_ids('["c1", "c2"]') == ["c1", "c2"]
    assert parse_published_comment_ids("not-json") == []



def test_public_comments_never_echo_spreadsheet_editorial_title():
    editorial_title = "سؤال عن التهديد بإفشاء الأسرار — زاوية جديدة: Checklist عملية قبل بدء أي إجراء"
    comments = build_video_comment_bundle(
        topic=editorial_title,
        article_url="https://askmahmoudkhyrat.blogspot.com/2026/11/confidentiality.html",
        video_id="secret_threat_reel",
        platform="facebook",
    )
    combined = " ".join(comments)
    assert "زاوية جديدة" not in combined
    assert "Checklist" not in combined
    assert "سؤال عن التهديد بإفشاء الأسرار" not in combined
    assert comments[0].endswith("؟") and "التهديد" in comments[0]
    assert "الدليل" in comments[1]
    assert any("askmahmoudkhyrat.blogspot.com" in item for item in comments)


def test_public_comments_are_standalone_and_professional_for_secret_threat_topic():
    comments = build_video_comment_bundle(
        topic="التهديد بإفشاء الأسرار — زاوية جديدة: Checklist عملية",
        article_url="https://askmahmoudkhyrat.blogspot.com/2026/11/confidentiality.html",
        video_id="secret_threat_reel_youtube",
        platform="youtube",
    )
    assert comments[0].endswith("؟") and "التهديد" in comments[0]
    assert any("الدليل الإلكتروني" in item or "الدليل" in item for item in comments)
    assert all("سؤال عن" not in item and "زاوية جديدة" not in item for item in comments)
