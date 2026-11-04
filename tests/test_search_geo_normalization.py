from search_geo import _clean, _slug


def test_search_geo_normalizes_html_and_whitespace():
    assert _clean("<p>سؤال   قانوني</p>") == "سؤال قانوني"
    assert _clean("<script>alert('x')</script>نص") == "نص"


def test_search_geo_slug_removes_punctuation_and_normalizes_spaces():
    assert _slug("ما الحكم القانوني؟ في مصر") == "ما-الحكم-القانوني-في-مصر"
