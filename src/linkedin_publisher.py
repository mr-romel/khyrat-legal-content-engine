from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


LINKEDIN_VERSION = "202607"
REST_PROTOCOL = "2.0.0"

BASE = "https://api.linkedin.com/rest"


class LinkedInPublishError(RuntimeError):
    """LinkedIn API operation failed."""


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


def initialize_image_upload(
    *,
    token: str,
    owner_urn: str,
) -> tuple[str, str]:

    response = requests.post(
        f"{BASE}/images?action=initializeUpload",
        headers=_headers(
            token,
            json_content=True,
        ),
        json={
            "initializeUploadRequest": {
                "owner": owner_urn,
            }
        },
        timeout=60,
    )

    if not response.ok:
        _raise(
            "LinkedIn image initialization",
            response,
        )

    value = response.json().get(
        "value",
        {},
    )

    upload_url = str(
        value.get("uploadUrl", "")
    ).strip()

    image_urn = str(
        value.get("image", "")
    ).strip()

    if not upload_url or not image_urn:
        raise LinkedInPublishError(
            f"Invalid image initialization response: "
            f"{response.json()}"
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

    response = requests.put(
        upload_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "image/jpeg",
        },
        data=image.read_bytes(),
        timeout=180,
    )

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

    response = requests.post(
        f"{BASE}/posts",
        headers=_headers(
            token,
            json_content=True,
        ),
        json={
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
                    "altText": (
                        "Legal educational image"
                    ),
                }
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        },
        timeout=60,
    )

    if not response.ok:
        _raise(
            "LinkedIn post creation",
            response,
        )

    post_urn = (
        response.headers.get("x-restli-id", "")
        or response.headers.get(
            "X-RestLi-Id",
            "",
        )
    ).strip()

    if not post_urn:
        raise LinkedInPublishError(
            "LinkedIn created post but returned no URN."
        )

    return post_urn


def add_comment(
    *,
    token: str,
    actor_urn: str,
    post_urn: str,
    message: str,
) -> LinkedInActionResult:

    endpoint = (
        f"{BASE}/socialActions/"
        f"{post_urn}/comments"
    )

    try:
        response = requests.post(
            endpoint,
            headers=_headers(
                token,
                json_content=True,
            ),
            json={
                "actor": actor_urn,
                "object": post_urn,
                "message": {
                    "text": message,
                },
            },
            timeout=60,
        )

        if not response.ok:
            return LinkedInActionResult(
                status="NOT_AUTHORIZED_OR_FAILED",
                error=str(
                    _payload(response)
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

    except requests.RequestException as exc:
        return LinkedInActionResult(
            status="FAILED",
            error=str(exc),
        )


def like_post(
    *,
    token: str,
    actor_urn: str,
    post_urn: str,
) -> LinkedInActionResult:

    endpoint = f"{BASE}/reactions"

    try:
        response = requests.post(
            endpoint,
            headers=_headers(
                token,
                json_content=True,
            ),
            json={
                "actor": actor_urn,
                "root": post_urn,
                "reactionType": "LIKE",
            },
            timeout=60,
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

    except requests.RequestException as exc:
        return LinkedInActionResult(
            status="FAILED",
            error=str(exc),
        )


def publish_to_linkedin(
    *,
    token: str,
    author_urn: str,
    image_path: str | Path,
    commentary: str,
    first_comment: str,
) -> dict[str, Any]:

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
