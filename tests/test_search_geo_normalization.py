from search_geo import _clean, _slug


def test_search_geo_normalizes_html_and_whitespace():
    assert _clean("<p>سؤال   قانوني</p>") == "سؤال قانوني"
    assert _clean("<script>alert('x')</script>نص") == "نص"


def test_search_geo_slug_removes_punctuation_and_normalizes_spaces():
    assert _slug("ما الحكم القانوني؟ في مصر") == "ما-الحكم-القانوني-في-مصر"


def test_live_page_metadata_uses_actual_reviewed_article_fields():
    from search_geo import build_live_page_metadata

    metadata = build_live_page_metadata(
        title="عنوان المقال",
        description="وصف المقال",
        answer="الإجابة المباشرة من المقال.",
        topic="قانون الشركات",
        keywords=["قانون الشركات", "قانون الشركات", "عقود"],
    )
    assert metadata["title"] == "عنوان المقال"
    assert metadata["description"] == "وصف المقال"
    assert metadata["answer"] == "الإجابة المباشرة من المقال."
    assert metadata["keywords"] == ["قانون الشركات", "عقود"]
    assert metadata["jurisdiction"] == "مصر"


def test_live_page_metadata_rejects_missing_article_answer():
    import pytest
    from search_geo import build_live_page_metadata

    with pytest.raises(ValueError):
        build_live_page_metadata(title="عنوان", description="", answer="", topic="موضوع")
