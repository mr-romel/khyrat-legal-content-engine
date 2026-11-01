from scripts.backfill_blogger_search_descriptions import build_search_description


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
