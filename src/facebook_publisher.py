from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


class FacebookPublishError(RuntimeError):
    pass


def publish_photo(
    *,
    page_id: str,
    page_access_token: str,
    graph_version: str,
    image_path: str | Path,
    caption: str,
) -> dict[str, Any]:

    page_id = (
        page_id or ""
    ).strip()

    page_access_token = (
        page_access_token or ""
    ).strip()

    graph_version = (
        graph_version or ""
    ).strip().lstrip("v")

    image = Path(
        image_path
    )

    if not page_id:
        raise FacebookPublishError(
            "FACEBOOK_PAGE_ID is empty."
        )

    if not page_access_token:
        raise FacebookPublishError(
            "FACEBOOK_PAGE_ACCESS_TOKEN is empty."
        )

    if not image.is_file():
        raise FacebookPublishError(
            f"Image does not exist: {image}"
        )

    endpoint = (
        f"https://graph.facebook.com/"
        f"v{graph_version}/"
        f"{page_id}/photos"
    )

    try:

        with image.open("rb") as file_handle:

            response = requests.post(
                endpoint,

                data={
                    "access_token":
                        page_access_token,

                    "caption":
                        caption,

                    "published":
                        "true",
                },

                files={
                    "source": (
                        image.name,
                        file_handle,
                        "image/jpeg",
                    )
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
            "Facebook returned invalid JSON."
        ) from exc

    if (
        not response.ok
        or "error" in payload
    ):

        error = payload.get(
            "error",
            {},
        )

        message = error.get(
            "message",
            "Unknown Facebook API error.",
        )

        code = error.get(
            "code"
        )

        subcode = error.get(
            "error_subcode"
        )

        raise FacebookPublishError(
            "Facebook API rejected the publish request: "
            f"{message} "
            f"(code={code}, subcode={subcode})"
        )

    post_id = (
        payload.get("post_id")
        or payload.get("id")
    )

    if not post_id:

        raise FacebookPublishError(
            "Facebook response did not contain a Post ID."
        )

    return {
        "post_id":
            str(post_id),

        "photo_id":
            str(
                payload.get("id")
            )
            if payload.get("id")
            else "",

        "raw":
            payload,
    }
