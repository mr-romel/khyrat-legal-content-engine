import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from backfill_blogger_search_descriptions import build_search_description, _existing_row_seo_fields


def test_prefers_article_answer_section_and_limits_length():
    html = (
        "<h2>الإجابة المختصرة</h2><p>يحق للعامل المطالبة بمستحقاته المالية "
        "وفقًا للقواعد القانونية المنظمة لعلاقة العمل والمستندات المثبتة للحقوق.</p>"
        "<h2>التفاصيل</h2><p>تفاصيل إضافية طويلة.</p>"
    )
    result = build_search_description(html, "مستحقات العامل")
    assert result.startswith("يحق للعامل")
    assert len(result) <= 150


def test_does_not_create_description_from_empty_or_markup_only_content():
    assert build_search_description("<div></div>", "عنوان المقال") == ""


def test_existing_legacy_row_is_normalized_for_seo_worker_selection():
    fields = _existing_row_seo_fields(
        {"Blogger Status": "DRAFT"},
        "123456789", "https://example.com/legal-post", "عنوان قانوني",
        "وصف قانوني واضح يشرح للقارئ موضوع المقال والإجراء الصحيح المتاح له.",
        "LEGACY SEO BACKFILL",
    )
    assert fields["Blogger Status"] == "PUBLISHED"
    assert fields["Blogger Post ID"] == "123456789"
    assert fields["Blogger URL"] == "https://example.com/legal-post"
    assert fields["Blogger SEO Status"] == "PENDING"
    assert len(fields["Blogger Meta Description"]) <= 150
