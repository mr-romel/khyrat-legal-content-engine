import blogger_seo_worker


class FakeField:
    def __init__(self, value):
        self.value = value

    def input_value(self, timeout=None):
        return self.value

    def inner_text(self, timeout=None):
        return self.value


def test_search_description_verification_reads_saved_blogger_editor_field(monkeypatch):
    monkeypatch.setattr(blogger_seo_worker, "_open_post_settings", lambda _page: FakeField("وصف قانوني محفوظ بالفعل"))
    assert blogger_seo_worker._read_editor_description(object()) == "وصف قانوني محفوظ بالفعل"


def test_public_captcha_does_not_override_authenticated_editor_verification(monkeypatch):
    class Response:
        ok = True
        text = "Our systems have detected unusual traffic. Please verify you are human."

    monkeypatch.setattr(blogger_seo_worker.requests, "get", lambda *args, **kwargs: Response())
    assert blogger_seo_worker._read_public_meta_http("https://example.blogspot.com/post") == ""


def test_public_meta_is_used_as_secondary_confirmation(monkeypatch):
    class Response:
        ok = True
        text = '<html><head><meta name="description" content="وصف قانوني صحيح"></head></html>'

    monkeypatch.setattr(blogger_seo_worker.requests, "get", lambda *args, **kwargs: Response())
    assert blogger_seo_worker._read_public_meta_http("https://example.blogspot.com/post") == "وصف قانوني صحيح"
