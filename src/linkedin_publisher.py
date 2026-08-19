from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


LINKEDIN_VERSION = "202607"
REST_PROTOCOL_VERSION = "2.0.0"

LINKEDIN_REST_BASE = "https://api.linkedin.com/rest"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"


class LinkedInPublishError(RuntimeError):
    """Raised when LinkedIn publishing fails."""


class LinkedInActionResult:
    def __init__(
        self,
        status: str,
        item_id: str = "",
        error: str = "",
    ) -> None:
        self.status = status
        self.item_id = item_id
        self.error = error

    def as_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "id": self.item_id,
            "error": self.error,
        }


def _headers(
    access_token: str,
    json_content: bool = False,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Linkedin-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": REST_PROTOCOL_VERSION,
    }

    if json_content:
        headers["Content-Type"] = "application/json"

    return headers


def _error_payload(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _raise_api_error(
    response: requests.Response,
    action: str,
) -> None:
    payload = _error_payload(response)

    raise LinkedInPublishError(
        f"{action} failed "
        f"(HTTP {response.status_code}): {payload}"
    )


def resolve_member_urn(
    access_token: str,
) -> str:
    """
    Resolve authenticated member to:
    urn:li:person:{sub}

    Requires an OpenID-enabled token.
    """

    try:
        response = requests.get(
            LINKEDIN_USERINFO_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise LinkedInPublishError(
            f"LinkedIn userinfo request failed: {exc}"
        ) from exc

    if not response.ok:
        _raise_api_error(
            response,
            "LinkedIn userinfo",
        )

    payload = response.json()

    sub = str(
        payload.get("sub", "")
    ).strip()

    if not sub:
        raise LinkedInPublishError(
            "LinkedIn userinfo did not return 'sub'. "
            "The token may not include OpenID."
        )

    return f"urn:li:person:{sub}"


def initialize_image_upload(
    access_token: str,
    author_urn: str,
) -> tuple[str, str]:

    url = (
        f"{LINKEDIN_REST_BASE}"
        "/images?action=initializeUpload"
    )

    body = {
        "initializeUploadRequest": {
            "owner": author_urn,
        }
    }

    try:
        response = requests.post(
            url,
            headers=_headers(
                access_token,
                json_content=True,
            ),
            json=body,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise LinkedInPublishError(
            f"LinkedIn image initialization failed: {exc}"
        ) from exc

    if not response.ok:
        _raise_api_error(
            response,
            "LinkedIn image initialization",
        )

    payload = response.json()
    value = payload.get("value", {})

    upload_url = str(
        value.get("uploadUrl", "")
    ).strip()

    image_urn = str(
        value.get("image", "")
    ).strip()

    if not upload_url or not image_urn:
        raise LinkedInPublishError(
            f"LinkedIn image initialization returned "
            f"invalid data: {payload}"
        )

    return upload_url, image_urn


def upload_image(
    access_token: str,
    upload_url: str,
    image_path: str | Path,
) -> None:

    image = Path(image_path)

    if not image.is_file():
        raise LinkedInPublishError(
            f"LinkedIn image does not exist: {image}"
        )

    content = image.read_bytes()

    try:
        response = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "image/jpeg",
            },
            data=content,
            timeout=180,
        )
    except requests.RequestException as exc:
        raise LinkedInPublishError(
            f"LinkedIn image upload failed: {exc}"
        ) from exc

    if not response.ok:
        _raise_api_error(
            response,
            "LinkedIn image upload",
        )


def create_post(
    access_token: str,
    author_urn: str,
    commentary: str,
    image_urn: str,
) -> str:

    url = f"{LINKEDIN_REST_BASE}/posts"

    body = {
        "author": author_urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "content": {
            "media": {
                "id": image_urn,
                "altText": "Legal educational image",
            }
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    try:
        response = requests.post(
            url,
            headers=_headers(
                access_token,
                json_content=True,
            ),
            json=body,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise LinkedInPublishError(
            f"LinkedIn post request failed: {exc}"
        ) from exc

    if not response.ok:
        _raise_api_error(
            response,
            "LinkedIn post creation",
        )

    post_urn = (
        response.headers.get("x-restli-id", "")
        or response.headers.get("X-RestLi-Id", "")
    ).strip()

    if not post_urn:
        raise LinkedInPublishError(
            "LinkedIn created the post but returned no post URN."
        )

    return post_urn


def create_comment(
    access_token: str,
    actor_urn: str,
    post_urn: str,
    message: str,
) -> LinkedInActionResult:

    url = (
        f"{LINKEDIN_REST_BASE}/socialActions/"
        f"{post_urn}/comments"
    )

    body = {
        "actor": actor_urn,
        "object": post_urn,
        "message": {
            "text": message,
        },
    }

    try:
        response = requests.post(
            url,
            headers=_headers(
                access_token,
                json_content=True,
            ),
            json=body,
            timeout=60,
        )
    except requests.RequestException as exc:
        return LinkedInActionResult(
            status="FAILED",
            error=str(exc),
        )

    if not response.ok:
        return LinkedInActionResult(
            status="NOT_AUTHORIZED_OR_FAILED",
            error=(
                f"HTTP {response.status_code}: "
                f"{_error_payload(response)}"
            ),
        )

    comment_id = (
        response.headers.get("x-restli-id", "")
        or response.headers.get("X-RestLi-Id", "")
    ).strip()

    return LinkedInActionResult(
        status="PUBLISHED",
        item_id=comment_id,
    )


def create_like(
    access_token: str,
    actor_urn: str,
    post_urn: str,
) -> LinkedInActionResult:

    url = f"{LINKEDIN_REST_BASE}/reactions"

    body = {
        "root": post_urn,
        "actor": actor_urn,
        "reactionType": "LIKE",
    }

    try:
        response = requests.post(
            url,
            headers=_headers(
                access_token,
                json_content=True,
            ),
            json=body,
            timeout=60,
        )
    except requests.RequestException as exc:
        return LinkedInActionResult(
            status="FAILED",
            error=str(exc),
        )

    if not response.ok:
        return LinkedInActionResult(
            status="NOT_AUTHORIZED_OR_FAILED",
            error=(
                f"HTTP {response.status_code}: "
                f"{_error_payload(response)}"
            ),
        )

    return LinkedInActionResult(
        status="LIKED",
    )


def publish_to_linkedin(
    access_token: str,
    author_urn: str,
    image_path: str | Path,
    commentary: str,
    first_comment: str,
) -> dict[str, Any]:

    upload_url, image_urn = initialize_image_upload(
        access_token=access_token,
        author_urn=author_urn,
    )

    upload_image(
        access_token=access_token,
        upload_url=upload_url,
        image_path=image_path,
    )

    post_urn = create_post(
        access_token=access_token,
        author_urn=author_urn,
        commentary=commentary,
        image_urn=image_urn,
    )

    comment = create_comment(
        access_token=access_token,
        actor_urn=author_urn,
        post_urn=post_urn,
        message=first_comment,
    )

    like = create_like(
        access_token=access_token,
        actor_urn=author_urn,
        post_urn=post_urn,
    )

    return {
        "image_urn": image_urn,
        "post_urn": post_urn,
        "comment": comment.as_dict(),
        "like": like.as_dict(),
    }
