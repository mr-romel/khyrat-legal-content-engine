from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


LINKEDIN_VERSION = "202607"
REST_PROTOCOL = "2.0.0"

LINKEDIN_REST_BASE = "https://api.linkedin.com/rest"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"


class LinkedInPublishError(RuntimeError):
    pass


class LinkedInActionResult:
    def __init__(
        self,
        *,
        status: str,
        id: str = "",
        error: str = "",
    ) -> None:
        self.status = status
        self.id = id
        self.error = error

    def as_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "id": self.id,
            "error": self.error,
        }


def _headers(
    access_token: str,
    *,
    json_content: bool = False,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Linkedin-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": REST_PROTOCOL,
    }

    if json_content:
        headers["Content-Type"] = "application/json"

    return headers


def _raise_api_error(
    response: requests.Response,
    context: str,
) -> None:
    try:
        payload: Any = response.json()
    except ValueError:
        payload = response.text

    raise LinkedInPublishError(
        f"{context} failed "
        f"(HTTP {response.status_code}): {payload}"
    )


def resolve_member_urn(
    access_token: str,
) -> str:
    """
    Resolve the authenticated LinkedIn member to:
    urn:li:person:{sub}

    Requires an OpenID-enabled token. If the current token does not
    include OpenID, callers can fall back to LINKEDIN_AUTHOR_URN.
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
            "LinkedIn userinfo response did not contain 'sub'."
        )

    return f"urn:li:person:{sub}"


def initialize_image_upload(
    *,
    access_token: str,
    author_urn: str,
) -> tuple[str, str]:
    """
    Register the image upload and return:
        (upload_url, image_urn)
    """
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
            f"LinkedIn image initialization returned no upload URL/image URN: "
            f"{payload}"
        )

    return upload_url, image_urn


def upload_image(
    *,
    access_token: str,
    upload_url: str,
    image_path: str | Path,
) -> None:
    """
    Upload the actual bytes to LinkedIn's temporary upload URL.
    """
    image = Path(image_path)

    if not image.is_file():
        raise LinkedInPublishError(
            f"LinkedIn image file does not exist: {image}"
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
    *,
    access_token: str,
    author_urn: str,
    commentary: str,
    image_urn: str,
) -> str:
    """
    Create a PUBLIC image post using the current Posts API.
    Returns the LinkedIn post URN.
    """
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
                "altText": "Legal educational image",
                "id": image_urn,
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

    post_id = (
        response.headers.get("x-restli-id", "")
        or response.headers.get("X-RestLi-Id", "")
    ).strip()

    if not post_id:
        raise LinkedInPublishError(
            "LinkedIn created the post but returned no x-restli-id."
        )

    return post_id


def create_comment(
    *,
    access_token: str,
    actor_urn: str,
    post_urn: str,
    message: str,
) -> LinkedInActionResult:
    """
    Best-effort first-level comment.
    Requires w_member_social_feed.
    """
    url = (
        f"{LINKEDIN_REST_BASE}/socialActions/"
        f"{quote(post_urn, safe='')}/comments"
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
        try:
            payload = response.json()
        except ValueError:
            payload = response.text

        return LinkedInActionResult(
            status="NOT_AUTHORIZED_OR_FAILED",
            error=(
                f"HTTP {response.status_code}: "
                f"{payload}"
            ),
        )

    comment_id = (
        response.headers.get("x-restli-id", "")
        or response.headers.get("X-RestLi-Id", "")
    ).strip()

    return LinkedInActionResult(
        status="PUBLISHED",
        id=comment_id,
    )


def create_like(
    *,
    access_token: str,
    actor_urn: str,
    post_urn: str,
) -> LinkedInActionResult:
    """
    Best-effort LIKE reaction.
    Requires w_member_social_feed.
    """
    url = (
        f"{LINKEDIN_REST_BASE}/reactions"
        f"?actor={quote(actor_urn, safe='')}"
    )

    body = {
        "root": post_urn,
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
        try:
            payload = response.json()
        except ValueError:
            payload = response.text

        return LinkedInActionResult(
            status="NOT_AUTHORIZED_OR_FAILED",
            error=(
                f"HTTP {response.status_code}: "
                f"{payload}"
            ),
        )

    reaction_id = ""

    try:
        payload = response.json()
        reaction_id = str(
            payload.get("id", "")
        ).strip()
    except ValueError:
        pass

    return LinkedInActionResult(
        status="LIKED",
        id=reaction_id,
    )


def publish_to_linkedin(
    *,
    access_token: str,
    author_urn: str,
    image_path: str | Path,
    commentary: str,
    first_comment: str,
) -> dict[str, Any]:
    """
    Full LinkedIn member publishing pipeline.

    Required:
      - image upload
      - image post

    Best effort:
      - first comment
      - LIKE reaction
    """

    if not access_token.strip():
        raise LinkedInPublishError(
            "LinkedIn access token is empty."
        )

    if not author_urn.strip():
        raise LinkedInPublishError(
            "LinkedIn author URN is empty."
        )

    # 1. Register image.
    upload_url, image_urn = initialize_image_upload(
        access_token=access_token,
        author_urn=author_urn,
    )

    # 2. Upload image.
    upload_image(
        access_token=access_token,
        upload_url=upload_url,
        image_path=image_path,
    )

    # LinkedIn may need a short moment before the media becomes usable.
    time.sleep(2)

    # 3. Create post.
    post_urn = create_post(
        access_token=access_token,
        author_urn=author_urn,
        commentary=commentary,
        image_urn=image_urn,
    )

    # 4. First comment — best effort.
    comment_result = create_comment(
        access_token=access_token,
        actor_urn=author_urn,
        post_urn=post_urn,
        message=first_comment,
    )

    # 5. Like — best effort.
    like_result = create_like(
        access_token=access_token,
        actor_urn=author_urn,
        post_urn=post_urn,
    )

    return {
        "image_urn": image_urn,
        "post_urn": post_urn,
        "comment": comment_result.as_dict(),
        "like": like_result.as_dict(),
    }
