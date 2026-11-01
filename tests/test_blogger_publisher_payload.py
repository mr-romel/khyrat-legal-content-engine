from blogger_publisher import build_blogger_post_payload


def test_blogger_post_payload_uses_valid_comment_enum():
    payload = build_blogger_post_payload("عنوان", "<p>محتوى</p>", ["قانون مصر"])
    assert payload["readerComments"] == "ALLOW"
    assert payload["title"] == "عنوان"
    assert payload["labels"] == ["قانون مصر"]
    assert "readerComments" not in {key: value for key, value in payload.items() if value == "allow"}
