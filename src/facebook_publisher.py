from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


class FacebookPublishError(RuntimeError):
    """Facebook API operation failed."""


def _api_error(action: str, response: requests.Response) -> FacebookPublishError:
    try:
        payload = response.json()
    except ValueError:
        payload = response.text
    return FacebookPublishError(f"{action}: {payload}")


def _headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def publish_photo(*, page_id: str, page_access_token: str, graph_version: str, image_path: str | Path, caption: str) -> dict[str, Any]:
    page_id = page_id.strip()
    page_access_token = page_access_token.strip()
    graph_version = graph_version.strip().lstrip("v")
    image = Path(image_path)
    if not page_id:
        raise FacebookPublishError("FACEBOOK_PAGE_ID is empty.")
    if not page_access_token:
        raise FacebookPublishError("FACEBOOK_PAGE_ACCESS_TOKEN is empty.")
    if not image.is_file():
        raise FacebookPublishError(f"Image does not exist: {image}")
    endpoint = f"https://graph.facebook.com/v{graph_version}/{page_id}/photos"
    try:
        with image.open("rb") as file_handle:
            response = requests.post(
                endpoint,
                headers=_headers(),
                data={"access_token": page_access_token, "caption": caption, "published": "true"},
                files={"source": (image.name, file_handle, "image/jpeg")},
                timeout=180,
            )
    except requests.RequestException as exc:
        raise FacebookPublishError(f"Facebook publish network error: {exc}") from exc
    if not response.ok:
        raise _api_error("Facebook publish failed", response)
    payload = response.json()
    post_id = (payload.get("post_id") or payload.get("id") or "").strip()
    if not post_id:
        raise FacebookPublishError(f"Facebook returned no Post ID: {payload}")
    return {"post_id": post_id, "raw": payload}


def like_comment(*, comment_id: str, page_access_token: str, graph_version: str) -> dict[str, Any]:
    comment_id = str(comment_id or "").strip()
    endpoint = f"https://graph.facebook.com/v{graph_version.strip().lstrip('v')}/{comment_id}/likes"
    if not comment_id:
        return {"status": "FAILED", "error": "Facebook comment ID is empty."}
    try:
        response = requests.post(endpoint, headers=_headers(), data={"access_token": page_access_token.strip()}, timeout=60)
    except requests.RequestException as exc:
        return {"status": "FAILED", "error": str(exc)}
    if not response.ok:
        return {"status": "FAILED", "error": _api_error("Facebook comment like failed", response).args[0]}
    return {"status": "LIKED", "comment_id": comment_id, "raw": response.json()}


def add_comment(*, post_id: str, page_access_token: str, graph_version: str, message: str) -> dict[str, Any]:
    endpoint = f"https://graph.facebook.com/v{graph_version.strip().lstrip('v')}/{post_id}/comments"
    try:
        response = requests.post(
            endpoint,
            headers=_headers(),
            data={"access_token": page_access_token, "message": message},
            timeout=60,
        )
    except requests.RequestException as exc:
        return {"status": "FAILED", "error": str(exc), "published_count": 0, "liked_count": 0}
    if not response.ok:
        return {"status": "FAILED", "error": _api_error("Facebook comment failed", response).args[0], "published_count": 0, "liked_count": 0}
    payload = response.json()
    comment_id = str(payload.get("id", "")).strip()
    if not comment_id:
        return {"status": "FAILED", "error": f"Facebook returned no Comment ID: {payload}", "published_count": 0, "liked_count": 0}
    like = like_comment(comment_id=comment_id, page_access_token=page_access_token, graph_version=graph_version)
    return {
        "status": "PUBLISHED",
        "comment_id": comment_id,
        "published_count": 1,
        "liked_count": 1 if like.get("status") == "LIKED" else 0,
        "like_status": like.get("status"),
        "like_error": like.get("error", ""),
    }


def like_post(*, post_id: str, page_access_token: str, graph_version: str) -> dict[str, Any]:
    endpoint = f"https://graph.facebook.com/v{graph_version.strip().lstrip('v')}/{post_id}/likes"
    try:
        response = requests.post(endpoint, headers=_headers(), data={"access_token": page_access_token}, timeout=60)
    except requests.RequestException as exc:
        return {"status": "FAILED", "error": str(exc)}
    if not response.ok:
        return {"status": "FAILED", "error": _api_error("Facebook like failed", response).args[0]}
    return {"status": "LIKED", "raw": response.json()}
