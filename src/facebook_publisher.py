from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


class FacebookPublishError(RuntimeError):
    pass


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _parse_json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise FacebookPublishError(
            f"Facebook returned non-JSON response (HTTP {response.status_code})."
        ) from exc
    if not isinstance(payload, dict):
        raise FacebookPublishError("Facebook returned an unexpected response.")
    return payload


def _raise_api_error(prefix: str, response: requests.Response, payload: dict[str, Any]) -> None:
    if response.ok and "error" not in payload:
        return
    error = payload.get("error", {})
    message = error.get("message", "Unknown Facebook API error.")
    code = error.get("code")
    subcode = error.get("error_subcode")
    raise FacebookPublishError(
        f"{prefix}: {message} (code={code}, subcode={subcode})"
    )


def find_recent_matching_post(
    *,
    page_id: str,
    page_access_token: str,
    graph_version: str,
    caption: str,
    limit: int = 25,
) -> str:
    """Best-effort duplicate recovery by matching exact recent post text."""
    endpoint = f"https://graph.facebook.com/v{graph_version}/{page_id}/posts"
    response = requests.get(
        endpoint,
        headers=_headers(page_access_token),
        params={
            "fields": "id,message,created_time",
            "limit": str(limit),
        },
        timeout=60,
    )
    payload = _parse_json(response)
    if response.status_code >= 400 or "error" in payload:
        return ""

    for post in payload.get("data", []) or []:
        if not isinstance(post, dict):
            continue
        if (post.get("message") or "").strip() == caption.strip():
            return str(post.get("id", ""))
    return ""


def publish_photo(
    *,
    page_id: str,
    page_access_token: str,
    graph_version: str,
    image_path: str | Path,
    caption: str,
) -> dict[str, Any]:
    page_id = (page_id or "").strip()
    page_access_token = (page_access_token or "").strip()
    graph_version = (graph_version or "").strip().lstrip("v")
    image = Path(image_path)

    if not page_id:
        raise FacebookPublishError("FACEBOOK_PAGE_ID is empty.")
    if not page_access_token:
        raise FacebookPublishError("FACEBOOK_PAGE_ACCESS_TOKEN is empty.")
    if not image.is_file():
        raise FacebookPublishError(f"Image does not exist: {image}")

    recovered_id = find_recent_matching_post(
        page_id=page_id,
        page_access_token=page_access_token,
        graph_version=graph_version,
        caption=caption,
    )
    if recovered_id:
        return {
            "post_id": recovered_id,
            "photo_id": "",
            "duplicate_recovered": True,
            "raw": {"recovered": True, "post_id": recovered_id},
        }

    endpoint = (
        f"https://graph.facebook.com/v{graph_version}/{page_id}/photos"
    )

    try:
        with image.open("rb") as file_handle:
            response = requests.post(
                endpoint,
                headers=_headers(page_access_token),
                data={
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

    payload = _parse_json(response)
    _raise_api_error("Facebook publish failed", response, payload)

    post_id = payload.get("post_id") or payload.get("id")
    if not post_id:
        raise FacebookPublishError(
            f"Facebook published successfully but returned no Post ID: {payload}"
        )

    return {
        "post_id": str(post_id),
        "photo_id": str(payload.get("id", "")),
        "duplicate_recovered": False,
        "raw": payload,
    }


def create_first_comment(
    *,
    post_id: str,
    page_access_token: str,
    graph_version: str,
    message: str,
) -> str:
    endpoint = f"https://graph.facebook.com/v{graph_version}/{post_id}/comments"
    response = requests.post(
        endpoint,
        headers=_headers(page_access_token),
        data={"message": message},
        timeout=60,
    )
    payload = _parse_json(response)
    _raise_api_error("Facebook comment failed", response, payload)
    return str(payload.get("id", ""))


def like_post(
    *,
    post_id: str,
    page_access_token: str,
    graph_version: str,
) -> bool:
    endpoint = f"https://graph.facebook.com/v{graph_version}/{post_id}/likes"
    response = requests.post(
        endpoint,
        headers=_headers(page_access_token),
        timeout=60,
    )
    payload = _parse_json(response)
    _raise_api_error("Facebook like failed", response, payload)
    return bool(payload.get("success", True))
