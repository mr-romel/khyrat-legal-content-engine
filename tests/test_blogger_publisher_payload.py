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


def test_article_schema_uses_live_author_profile_page_and_official_profiles():
    import json
    from blogger_publisher import build_article_html

    html = build_article_html(
        "عنوان قانوني", "موضوع", "نص قانوني", "", "", [],
        article={"lead": "مقدمة", "meta_description": "وصف قانوني", "sections": []},
    )
    raw = html.split('type="application/ld+json">', 1)[1].split("</script>", 1)[0]
    schema = json.loads(raw)
    graph = schema["@graph"]
    post = next(item for item in graph if item.get("@type") == "BlogPosting")
    author = post["author"]
    assert author["url"] == "https://askmahmoudkhyrat.blogspot.com/p/blog-page_07.html"
    assert "https://www.facebook.com/AskMahmoudNow" in author["sameAs"]
    assert "https://www.linkedin.com/in/mahmoud-khyrat" in author["sameAs"]
    assert "https://www.youtube.com/@everything101-mhrm" in author["sameAs"]
