from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


DEFAULT_VERSION = "202607"
BASE_URL = "https://api.linkedin.com/rest"


class LinkedInPublishError(RuntimeError):
    pass


def _headers(token: str, version: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Linkedin-Version": version,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }


def _json_or_text(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _check(response: requests.Response, action: str) -> Any:
    payload = _json_or_text(response)
    if response.status_code >= 400:
        raise LinkedInPublishError(
            f"LinkedIn {action} failed: HTTP {response.status_code} - {payload}"
        )
    return payload


def initialize_image_upload(
    *, token: str, author_urn: str, version: str = DEFAULT_VERSION
) -> dict[str, Any]:
    response = requests.post(
        f"{BASE_URL}/images?action=initializeUpload",
        headers=_headers(token, version),
        json={"initializeUploadRequest": {"owner": author_urn}},
        timeout=60,
    )
    payload = _check(response, "image initialization")
    return payload.get("value", payload)


def upload_image(
    *, upload_url: str, image_path: str | Path, token: str
) -> None:
    image = Path(image_path)
    if not image.is_file():
        raise LinkedInPublishError(f"LinkedIn image file does not exist: {image}")
    with image.open("rb") as handle:
        response = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "image/jpeg",
            },
            data=handle,
            timeout=120,
        )
    if response.status_code >= 400:
        raise LinkedInPublishError(
            f"LinkedIn image upload failed: HTTP {response.status_code} - {_json_or_text(response)}"
        )


def create_post(
    *,
    token: str,
    author_urn: str,
    commentary: str,
    image_urn: str,
    version: str = DEFAULT_VERSION,
) -> str:
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
                "title": "Khyrat Legal Content",
                "id": image_urn,
            }
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    response = requests.post(
        f"{BASE_URL}/posts",
        headers=_headers(token, version),
        json=body,
        timeout=90,
    )
    _check(response, "post creation")
    post_id = response.headers.get("x-restli-id", "")
    if not post_id:
        try:
            post_id = response.json().get("id", "")
        except ValueError:
            post_id = ""
    if not post_id:
        raise LinkedInPublishError(
            "LinkedIn created the post but returned no post ID."
        )
    return str(post_id)


def create_comment(
    *,
    token: str,
    actor_urn: str,
    post_urn: str,
    message: str,
    version: str = DEFAULT_VERSION,
) -> str:
    encoded = quote(post_urn, safe="")
    response = requests.post(
        f"{BASE_URL}/socialActions/{encoded}/comments",
        headers=_headers(token, version),
        json={
            "actor": actor_urn,
            "object": post_urn,
            "message": {"text": message},
        },
        timeout=60,
    )
    payload = _check(response, "comment creation")
    if isinstance(payload, dict):
        comment_urn = payload.get("id") or payload.get("commentUrn")
        if comment_urn:
            return str(comment_urn)
    location = response.headers.get("x-restli-id", "")
    return str(location)


def like_post(
    *,
    token: str,
    actor_urn: str,
    post_urn: str,
    version: str = DEFAULT_VERSION,
) -> bool:
    encoded = quote(post_urn, safe="")
    response = requests.post(
        f"{BASE_URL}/socialActions/{encoded}/likes",
        headers=_headers(token, version),
        json={
            "actor": actor_urn,
            "object": post_urn,
        },
        timeout=60,
    )
    _check(response, "like creation")
    return True


def publish_image_post(
    *,
    token: str,
    author_urn: str,
    image_path: str | Path,
    commentary: str,
    version: str = DEFAULT_VERSION,
) -> dict[str, str]:
    upload = initialize_image_upload(
        token=token,
        author_urn=author_urn,
        version=version,
    )
    upload_url = upload.get("uploadUrl") or upload.get("upload_url")
    image_urn = upload.get("image") or upload.get("imageUrn")

    if not upload_url or not image_urn:
        raise LinkedInPublishError(
            f"LinkedIn initialization did not return upload URL and image URN: {upload}"
        )

    upload_image(
        upload_url=upload_url,
        image_path=image_path,
        token=token,
    )

    post_urn = create_post(
        token=token,
        author_urn=author_urn,
        commentary=commentary,
        image_urn=image_urn,
        version=version,
    )

    return {
        "image_urn": str(image_urn),
        "post_urn": post_urn,
    }
