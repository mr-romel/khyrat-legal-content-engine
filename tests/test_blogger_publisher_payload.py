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
