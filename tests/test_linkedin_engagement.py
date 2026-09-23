from unittest.mock import Mock, patch

from linkedin_comment_engine import choose_comment_count, comment_schedule_offsets
from linkedin_engagement import CapabilityResult, check_comment_capability, comment_fingerprint


def test_comment_fingerprint_is_stable():
    assert comment_fingerprint("urn:li:share:1", "hello") == comment_fingerprint("urn:li:share:1", "hello")
    assert comment_fingerprint("urn:li:share:1", "hello") != comment_fingerprint("urn:li:share:2", "hello")


def test_comment_count_is_always_between_5_and_8_and_stable():
    urn = "urn:li:share:123"
    assert 5 <= choose_comment_count(urn) <= 8
    assert choose_comment_count(urn) == choose_comment_count(urn)


def test_comment_count_can_vary_by_post():
    counts = {choose_comment_count(f"urn:li:share:{i}") for i in range(1, 500)}
    assert counts == set(range(5, 9))


def test_schedule_offsets_match_comment_count():
    assert comment_schedule_offsets(5) == [0, 15, 30, 45, 60]
    assert len(comment_schedule_offsets(8)) == 8
    assert comment_schedule_offsets(8) == sorted(comment_schedule_offsets(8))
    assert comment_schedule_offsets(8)[-1] == 105


def test_capability_uses_real_post_read_not_fake_post_write():
    response = Mock(status_code=200)
    with patch("linkedin_engagement.requests.get", return_value=response) as get:
        result = check_comment_capability(token="token", post_urn="urn:li:ugcPost:123")
    get.assert_called_once()
    assert isinstance(result, CapabilityResult)
    assert result.status == "READABLE"
    assert result.http_status == 200


def test_capability_403_is_permission_blocked():
    response = Mock(status_code=403)
    response.json.return_value = {"message": "Not enough permissions"}
    with patch("linkedin_engagement.requests.get", return_value=response):
        result = check_comment_capability(token="token", post_urn="urn:li:ugcPost:123")
    assert result.status == "BLOCKED_PERMISSION"
    assert result.http_status == 403


def test_capability_requires_real_post_urn():
    result = check_comment_capability(token="token", post_urn="")
    assert result.status == "POST_URN_MISSING"
