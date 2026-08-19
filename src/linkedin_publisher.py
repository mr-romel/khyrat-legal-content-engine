from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


LINKEDIN_VERSION = "202607"
REST_PROTOCOL = "2.0.0"

LINKEDIN_REST_BASE = "https://api.linkedin.com/rest"


class LinkedInPublishError(RuntimeError):
    """Raised when a required LinkedIn publishing operation fails."""


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
    *,
    json_content: bool = False,
) -> dict[str, str]:
    """
    Standard LinkedIn REST headers.
    """

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


def _raise_required_error(
    action: str,
    response: requests.Response,
) -> None:
    payload = _payload(response)

    raise LinkedInPublishError(
        f"{action} failed "
        f"(HTTP {response.status_code}): "
        f"{payload}"
    )


def initialize_image_upload(
    *,
    token: str,
    owner_urn: str,
) -> tuple[str, str]:
    """
    Initialize a LinkedIn image upload.

    Returns:
        upload_url, image_urn
    """

    endpoint = (
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
            endpoint,
            headers=_headers(
                token,
                json_content=True,
            ),
            json=body,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise LinkedInPublishError(
            f"LinkedIn image initialization network error: {exc}"
        ) from exc

    if not response.ok:
        _raise_required_error(
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

    if not upload_url:
        raise LinkedInPublishError(
            "LinkedIn image initialization returned no uploadUrl."
        )

    if not image_urn:
        raise LinkedInPublishError(
            "LinkedIn image initialization returned no image URN."
        )

    return upload_url, image_urn


def upload_image(
    *,
    token: str,
    upload_url: str,
    image_path: str | Path,
) -> None:
    """
    Upload the generated JPG to LinkedIn.
    """

    image = Path(image_path)

    if not image.is_file():
        raise LinkedInPublishError(
            f"LinkedIn image file not found: {image}"
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
            f"LinkedIn image upload network error: {exc}"
        ) from exc

    if not response.ok:
        _raise_required_error(
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
    """
    Publish the image + commentary as a public LinkedIn post.
    """

    endpoint = (
        f"{LINKEDIN_REST_BASE}/posts"
    )

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
            endpoint,
            headers=_headers(
                token,
                json_content=True,
            ),
            json=body,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise LinkedInPublishError(
            f"LinkedIn post network error: {exc}"
        ) from exc

    if not response.ok:
        _raise_required_error(
            "LinkedIn post creation",
            response,
        )

    post_urn = (
        response.headers.get(
            "x-restli-id",
            "",
        )
        or response.headers.get(
            "X-RestLi-Id",
            "",
        )
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
    """
    Best-effort first comment.

    If LinkedIn denies the social-feed permission, the post remains
    successful and this action is recorded as NOT_AUTHORIZED_OR_FAILED.
    """

    endpoint = (
        f"{LINKEDIN_REST_BASE}"
        f"/socialActions/"
        f"{post_urn}"
        f"/comments"
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
            endpoint,
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
            error=(
                f"HTTP {response.status_code}: "
                f"{_payload(response)}"
            ),
        )

    comment_id = (
        response.headers.get(
            "x-restli-id",
            "",
        )
        or response.headers.get(
            "X-RestLi-Id",
            "",
        )
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
    """
    Best-effort LIKE reaction.

    Current LinkedIn Reactions API format:
        POST /rest/reactions?actor=<encoded actor URN>

    Body:
        {
            "root": "<post URN>",
            "reactionType": "LIKE"
        }
    """

    encoded_actor = quote(
        actor_urn,
        safe="",
    )

    endpoint = (
        f"{LINKEDIN_REST_BASE}"
        f"/reactions?actor={encoded_actor}"
    )

    body = {
        "root": post_urn,
        "reactionType": "LIKE",
    }

    try:
        response = requests.post(
            endpoint,
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
            error=(
                f"HTTP {response.status_code}: "
                f"{_payload(response)}"
            ),
        )

    reaction_id = ""

    # LinkedIn may return the reaction resource in the body.
    try:
        payload = response.json()

        if isinstance(payload, dict):
            reaction_id = str(
                payload.get("id", "")
            ).strip()
    except ValueError:
        pass

    return LinkedInActionResult(
        status="LIKED",
        item_id=reaction_id,
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
    Full LinkedIn pipeline:

        1. Initialize image upload
        2. Upload image
        3. Publish post
        4. Add first comment (best effort)
        5. Like own post (best effort)

    The post is considered successful once step 3 succeeds.
    Steps 4 and 5 cannot roll back the post.
    """

    token = (token or "").strip()
    author_urn = (author_urn or "").strip()

    if not token:
        raise LinkedInPublishError(
            "LINKEDIN_ACCESS_TOKEN is empty."
        )

    if not author_urn:
        raise LinkedInPublishError(
            "LinkedIn author URN is empty."
        )

    # ------------------------------------------------------------
    # IMAGE
    # ------------------------------------------------------------

    upload_url, image_urn = initialize_image_upload(
        token=token,
        owner_urn=author_urn,
    )

    upload_image(
        token=token,
        upload_url=upload_url,
        image_path=image_path,
    )

    # ------------------------------------------------------------
    # POST
    # ------------------------------------------------------------

    post_urn = create_post(
        token=token,
        author_urn=author_urn,
        commentary=commentary,
        image_urn=image_urn,
    )

    # ------------------------------------------------------------
    # COMMENT
    # ------------------------------------------------------------

    comment = add_comment(
        token=token,
        actor_urn=author_urn,
        post_urn=post_urn,
        message=first_comment,
    )

    # ------------------------------------------------------------
    # LIKE
    # ------------------------------------------------------------

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
