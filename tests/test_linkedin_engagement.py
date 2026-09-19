from __future__ import annotations

from unittest.mock import Mock, patch

from linkedin_engagement import CapabilityResult, check_comment_capability, comment_fingerprint


def test_comment_fingerprint_is_stable():
    assert comment_fingerprint("urn:li:share:1", "hello") == comment_fingerprint("urn:li:share:1", "hello")
    assert comment_fingerprint("urn:li:share:1", "hello") != comment_fingerprint("urn:li:share:2", "hello")


def test_capability_403_is_permission_blocked():
    response = Mock(status_code=403)
    response.json.return_value = {"message": "Not enough permissions"}
    with patch("linkedin_engagement.requests.post", return_value=response):
        result = check_comment_capability(token="token")
    assert isinstance(result, CapabilityResult)
    assert result.status == "BLOCKED_PERMISSION"
    assert result.http_status == 403


def test_capability_404_is_probably_available_without_creating_comment():
    response = Mock(status_code=404)
    response.json.return_value = {"message": "Not found"}
    with patch("linkedin_engagement.requests.post", return_value=response) as post:
        result = check_comment_capability(token="token")
    post.assert_called_once()
    assert result.status == "PROBABLE_AVAILABLE"
    assert result.http_status == 404
