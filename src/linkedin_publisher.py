from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


LINKEDIN_VERSION = "202607"
REST_PROTOCOL = "2.0.0"

LINKEDIN_REST_BASE = "https://api.linkedin.com/rest"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"


class LinkedInPublishError(RuntimeError):
    """Raised when a LinkedIn operation fails."""


class LinkedInActionResult:
    def __init__(
        self,
        *,
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
    token: str,
    json_content: bool = False,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Linkedin-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": REST_PROTOCOL,
    }

    if json_content:
        headers["Content-Type"] = "application/json"

    return headers


def _payload(
    response: requests.Response,
) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _raise(
    action: str,
    response: requests.Response,
) -> None:
    raise LinkedInPublishError(
        f"{action} failed "
        f"(HTTP {response.status_code}): "
        f"{_payload(response)}"
    )


def resolve_member_urn(
    token: str,
) -> str:
    """
    Resolve the authenticated LinkedIn member automatically.

    Requires a token with OpenID access.
    """

    try:
        response = requests.get(
            LINKEDIN_USERINFO_URL,
            headers={
                "Authorization": f"Bearer {token}",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise LinkedInPublishError(
            f"LinkedIn userinfo request failed: {exc}"
        ) from exc

    if not response.ok:
        _raise(
            "LinkedIn userinfo",
            response,
        )

    payload = response.json()

    sub = str(
        payload.get("sub", "")
    ).strip()

    if not sub:
        raise LinkedInPublishError(
            "LinkedIn userinfo did not return a 'sub'. "
            "Make sure the access token includes "
            "openid and profile."
        )

    return f"urn:li:person:{sub}"


def initialize_image_upload(
    *,
    token: str,
    owner_urn: str,
) -> tuple[str, str]:
    url = (
        f"{LINKEDIN_REST_BASE}"
        "/images?action=initializeUpload"
    )

    body = {
        "initializeUploadRequest": {
            "owner": owner_urn,
        }
    }

    try:
        response = requests.post(
            url,
            headers=_headers(
                token,
                json_content=True,
            ),
            json=body,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise LinkedInPublishError(
            f"LinkedIn image initialization failed: {exc}"
        ) from exc

    if not response.ok:
        _raise(
            "LinkedIn image initialization",
            response,
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
            "LinkedIn image initialization returned "
            "an invalid upload URL or image URN."
        )

    return upload_url, image_urn


def upload_image(
    *,
    token: str,
    upload_url: str,
    image_path: str | Path,
) -> None:
    image = Path(image_path)

    if not image.is_file():
        raise LinkedInPublishError(
            f"LinkedIn image not found: {image}"
        )

    try:
        response = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "image/jpeg",
            },
            data=image.read_bytes(),
            timeout=180,
        )
    except requests.RequestException as exc:
        raise LinkedInPublishError(
            f"LinkedIn image upload failed: {exc}"
        ) from exc

    if not response.ok:
        _raise(
            "LinkedIn image upload",
            response,
        )


def create_post(
    *,
    token: str,
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
                token,
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
        _raise(
            "LinkedIn post creation",
            response,
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


def add_comment(
    *,
    token: str,
    actor_urn: str,
    post_urn: str,
    message: str,
) -> LinkedInActionResult:
    url = (
        f"{LINKEDIN_REST_BASE}"
        f"/socialActions/{post_urn}/comments"
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
                token,
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
            error=str(
                _payload(response)
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


def like_post(
    *,
    token: str,
    actor_urn: str,
    post_urn: str,
) -> LinkedInActionResult:
    url = f"{LINKEDIN_REST_BASE}/reactions"

    body = {
        "actor": actor_urn,
        "root": post_urn,
        "reactionType": "LIKE",
    }

    try:
        response = requests.post(
            url,
            headers=_headers(
                token,
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
            error=str(
                _payload(response)
            ),
        )

    return LinkedInActionResult(
        status="LIKED",
    )


def publish_to_linkedin(
    *,
    token: str,
    author_urn: str,
    image_path: str | Path,
    commentary: str,
    first_comment: str,
) -> dict[str, Any]:
    """
    Complete LinkedIn pipeline:
      image upload
      post publication
      comment best-effort
      like best-effort
    """

    upload_url, image_urn = initialize_image_upload(
        token=token,
        owner_urn=author_urn,
    )

    upload_image(
        token=token,
        upload_url=upload_url,
        image_path=image_path,
    )

    post_urn = create_post(
        token=token,
        author_urn=author_urn,
        commentary=commentary,
        image_urn=image_urn,
    )

    comment = add_comment(
        token=token,
        actor_urn=author_urn,
        post_urn=post_urn,
        message=first_comment,
    )

    like = like_post(
        token=token,
        actor_urn=author_urn,
        post_urn=post_urn,
    )

    return {
        "image_urn": image_urn,
        "post_urn": post_urn,
        "comment": comment.as_dict(),
        "like": like.as_dict(),
    }
