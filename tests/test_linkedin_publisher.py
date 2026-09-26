from unittest.mock import Mock, patch

from linkedin_publisher import LinkedInActionResult, add_comment, like_post


def _response(status_code, *, headers=None, json_payload=None):
    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.headers = headers or {}
    response.json.return_value = json_payload if json_payload is not None else {}
    response.text = ""
    return response


def test_personal_comment_uses_legacy_member_route_first():
    response = _response(
        201,
        headers={"x-restli-id": "123456789"},
    )
    with patch("linkedin_publisher.requests.post", return_value=response) as post:
        result = add_comment(
            token="token",
            actor_urn="urn:li:person:member123",
            post_urn="urn:li:share:post123",
            message="Test comment",
        )

    post.assert_called_once()
    assert "/rest/reactions?actor=" in post.call_args.args[0]
    assert result.status == "PUBLISHED"
    assert result.http_status == 201


def test_personal_comment_can_fall_back_to_versioned_rest():
    legacy = _response(
        403,
        json_payload={"message": "Not enough permissions"},
    )
    rest = _response(
        201,
        headers={"x-restli-id": "987654321"},
    )
    with patch("linkedin_publisher.requests.post", side_effect=[legacy, rest]) as post:
        result = add_comment(
            token="token",
            actor_urn="urn:li:person:member123",
            post_urn="urn:li:share:post123",
            message="Test comment",
        )

    assert post.call_count == 2
    assert "/v2/socialActions/" in post.call_args_list[0].args[0]
    assert "/rest/socialActions/" in post.call_args_list[1].args[0]
    assert result.status == "PUBLISHED"


def test_personal_like_uses_legacy_member_route_first():
    response = _response(
        201,
        json_payload={"id": "urn:li:like:(urn:li:person:member123,urn:li:share:post123)"},
    )
    with patch("linkedin_publisher.requests.post", return_value=response) as post:
        result = like_post(
            token="token",
            actor_urn="urn:li:person:member123",
            post_urn="urn:li:share:post123",
        )

    post.assert_called_once()
    assert "/rest/reactions?actor=" in post.call_args.args[0]
    assert result.status == "LIKED"
    assert result.http_status == 201
