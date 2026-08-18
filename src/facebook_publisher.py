"""Facebook Page publishing adapter for Khyrat Legal Content Engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


class FacebookPublishError(RuntimeError):
    """Raised when Facebook rejects a publish request."""


def publish_photo(
    *,
    page_id: str,
    page_access_token: str,
    graph_version: str,
    image_path: str | Path,
    caption: str,
) -> dict[str, Any]:
    """Publish a generated JPEG to a Facebook Page and return its IDs."""
    page_id = page_id.strip()
    page_access_token = page_access_token.strip()
    graph_version = graph_version.strip().lstrip("v")
    image = Path(image_path)

    if not page_id:
        raise FacebookPublishError("FACEBOOK_PAGE_ID is empty.")
    if not page_access_token:
        raise FacebookPublishError("FACEBOOK_PAGE_ACCESS_TOKEN is empty.")
    if not image.is_file():
        raise FacebookPublishError(f"Image file does not exist: {image}")

    endpoint = f"https://graph.facebook.com/v{graph_version}/{page_id}/photos"

    try:
        with image.open("rb") as file_handle:
            response = requests.post(
                endpoint,
                data={
                    "access_token": page_access_token,
                    "caption": caption,
                    "published": "true",
                },
                files={
                    "source": (image.name, file_handle, "image/jpeg"),
                },
                timeout=120,
            )
    except requests.RequestException as exc:
        raise FacebookPublishError(
            f"Facebook network request failed: {exc}"
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise FacebookPublishError(
            f"Facebook returned a non-JSON response (HTTP {response.status_code})."
        ) from exc

    if not response.ok or "error" in payload:
        error = payload.get("error", {})
        message = error.get("message", "Unknown Facebook API error.")
        code = error.get("code")
        subcode = error.get("error_subcode")
        details = f"code={code}"
        if subcode is not None:
            details += f", subcode={subcode}"
        raise FacebookPublishError(
            f"Facebook API rejected the publish request: {message} ({details})."
        )

    post_id = payload.get("post_id") or payload.get("id")
    if not post_id:
        raise FacebookPublishError(
            f"Facebook response did not contain a post identifier: {payload}"
        )

    return {
        "post_id": str(post_id),
        "photo_id": str(payload.get("id")) if payload.get("id") else "",
        "raw": payload,
    }
