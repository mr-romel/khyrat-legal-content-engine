from blogger_publisher import build_blogger_post_payload


def test_blogger_post_payload_uses_valid_comment_enum():
    payload = build_blogger_post_payload("عنوان", "<p>محتوى</p>", ["قانون مصر"])
    assert "readerComments" not in payload
    assert payload["title"] == "عنوان"
    assert payload["labels"] == ["قانون مصر"]
    assert "readerComments" not in {key: value for key, value in payload.items() if value == "allow"}


def test_blogger_labels_obey_utf8_byte_budget():
    from blogger_publisher import normalize_blogger_labels

    labels = normalize_blogger_labels([
        "ترند مصر", "مستجدات قانونية", "قانون مصر", "اسأل محمود",
        "كاميرات مراقبة الحضانات", "قانون الحضانات في مصر",
        "شروط ترخيص الحضانة", "القرارات الوزارية للحضانات", "غرامات الحضانات",
    ])
    assert labels
    assert sum(len(label.encode("utf-8")) for label in labels) <= 180


def test_blogger_labels_obey_utf8_byte_budget():
    from blogger_publisher import normalize_blogger_labels

    labels = normalize_blogger_labels([
        "ترند مصر", "مستجدات قانونية", "قانون مصر", "اسأل محمود",
        "كاميرات مراقبة الحضانات", "قانون الحضانات في مصر",
        "شروط ترخيص الحضانة", "القرارات الوزارية للحضانات", "غرامات الحضانات",
    ])
    assert labels
    assert sum(len(label.encode("utf-8")) for label in labels) + len(labels) - 1 <= 180


def test_article_schema_uses_blogger_safe_microdata_and_canonical_author_profile():
    from blogger_publisher import build_article_html

    content = build_article_html(
        "عنوان قانوني", "موضوع", "نص قانوني", "", "", [],
        article={"lead": "مقدمة", "meta_description": "وصف قانوني", "sections": []},
    )
    assert 'itemscope itemtype="https://schema.org/BlogPosting"' in content
    assert 'itemprop="author"' in content
    assert 'itemtype="https://schema.org/Person"' in content
    assert 'https://askmahmoudkhyrat.blogspot.com/p/blog-page_03.html' in content
    assert 'https://www.youtube.com/channel/UCc6NY-Y6w7can5GdTtLVtMA' in content
    assert 'itemprop="datePublished"' in content
    assert 'itemprop="dateModified"' in content
    assert 'itemprop="publisher"' in content
    assert 'itemprop="inLanguage" content="ar-EG"' in content
    assert 'itemprop="articleSection"' in content
    assert "<script" not in content.lower()


def test_official_profile_page_schema_connects_youtube_identity():
    import json
    from blogger_site_setup import PAGES

    about = next(page for page in PAGES if page["title"] == "من نحن")
    raw = about["content"].split('type="application/ld+json">', 1)[1].split("</script>", 1)[0]
    schema = json.loads(raw)
    person = schema["mainEntity"]
    assert person["name"] == "محمود خيرت رجب"
    assert "https://www.youtube.com/channel/UCc6NY-Y6w7can5GdTtLVtMA" in person["sameAs"]
    assert "https://www.facebook.com/AskMahmoudNow" in person["sameAs"]
    assert "https://www.linkedin.com/in/mahmoud-khyrat" in person["sameAs"]


def test_canonical_identity_page_has_profilepage_person_entity():
    from blogger_site_setup import PAGES

    identity = next(page for page in PAGES if page["title"] == "هوية اسأل محمود")
    assert '"@type":"ProfilePage"' in identity["content"]
    assert '"@type":"Person"' in identity["content"]
    assert 'blog-page_03.html#person' in identity["content"]
    assert "facebook.com/AskMahmoudNow" in identity["content"]
    assert "linkedin.com/in/mahmoud-khyrat" in identity["content"]
    assert "youtube.com/@everything101-mhrm" in identity["content"]
