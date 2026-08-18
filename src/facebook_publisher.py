from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


class FacebookPublishError(RuntimeError):
    pass


def _request(method: str, url: str, *, data: dict[str, Any] | None = None, files=None) -> dict[str, Any]:
    try:
        response = requests.request(method, url, data=data, files=files, timeout=120)
    except requests.RequestException as exc:
        raise FacebookPublishError(f"Facebook network request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise FacebookPublishError(
            f"Facebook returned non-JSON response (HTTP {response.status_code})."
        ) from exc

    if not response.ok or "error" in payload:
        error = payload.get("error", {})
        raise FacebookPublishError(
            f"Facebook API rejected request: {error.get('message', payload)} "
            f"(code={error.get('code')}, subcode={error.get('error_subcode')})"
        )
    return payload


def publish_photo(*, page_id: str, page_access_token: str, graph_version: str, image_path: str | Path, caption: str) -> dict[str, Any]:
    image = Path(image_path)
    if not image.is_file():
        raise FacebookPublishError(f"Image file does not exist: {image}")

    endpoint = f"https://graph.facebook.com/v{graph_version}/{page_id}/photos"
    with image.open("rb") as handle:
        payload = _request(
            "POST",
            endpoint,
            data={
                "access_token": page_access_token,
                "caption": caption,
                "published": "true",
            },
            files={"source": (image.name, handle, "image/jpeg")},
        )

    post_id = payload.get("post_id") or payload.get("id")
    if not post_id:
        raise FacebookPublishError(f"Facebook response did not contain a post ID: {payload}")
    return {"post_id": str(post_id), "photo_id": str(payload.get("id", "")), "raw": payload}


def add_first_comment(*, post_id: str, page_access_token: str, graph_version: str, comment: str) -> dict[str, Any]:
    endpoint = f"https://graph.facebook.com/v{graph_version}/{post_id}/comments"
    payload = _request(
        "POST",
        endpoint,
        data={"access_token": page_access_token, "message": comment},
    )
    return {"comment_id": str(payload.get("id", "")), "raw": payload}


def try_like_post(*, post_id: str, page_access_token: str, graph_version: str) -> dict[str, Any]:
    endpoint = f"https://graph.facebook.com/v{graph_version}/{post_id}/likes"
    try:
        payload = _request(
            "POST",
            endpoint,
            data={"access_token": page_access_token},
        )
        return {"ok": True, "raw": payload}
    except FacebookPublishError as exc:
        # Like is optional. Never fail a successful publication because Meta rejects this optional action.
        return {"ok": False, "error": str(exc)}
