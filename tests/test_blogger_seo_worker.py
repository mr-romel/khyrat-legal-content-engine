import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from blogger_seo_worker import _challenge_reason, _retry_is_due


class _Locator:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=2500):
        return self.text


class _Page:
    def __init__(self, url="", body=""):
        self.url = url
        self.body = body

    def locator(self, selector):
        return _Locator(self.body)


def test_detects_google_unusual_traffic_interstitial():
    page = _Page("https://www.google.com/sorry/index", "Our systems have detected unusual traffic")
    assert "paused" in _challenge_reason(page).lower()


def test_detects_arabic_captcha_interstitial():
    page = _Page("https://www.blogger.com/", "يرجى التحقق من أنك لست روبوت")
    assert _challenge_reason(page)


def test_does_not_flag_normal_blogger_editor():
    page = _Page("https://www.blogger.com/blog/post/edit/1/2", "Post settings Search description")
    assert _challenge_reason(page) == ""


def test_deferred_rate_limit_is_not_retried_before_cooldown():
    assert not _retry_is_due("RETRY_AFTER=2099-01-01T00:00:00+00:00 | paused")


def test_deferred_rate_limit_becomes_retryable_after_cooldown():
    assert _retry_is_due("RETRY_AFTER=2000-01-01T00:00:00+00:00 | paused")
