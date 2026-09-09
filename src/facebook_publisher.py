from __future__ import annotations

import json
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


def _graph_url(graph_version: str, object_id: str, edge: str = "") -> str:
    version = graph_version.strip().lstrip("v")
    suffix = f"/{edge.lstrip('/')}" if edge else ""
    return f"https://graph.facebook.com/v{version}/{object_id}{suffix}"


def _validate_page_token(*, page_id: str, page_access_token: str, graph_version: str) -> dict[str, Any]:
    response = requests.get(
        _graph_url(graph_version, "me"),
        headers=_headers(),
        params={"fields": "id,name", "access_token": page_access_token},
        timeout=30,
    )
    if not response.ok:
        raise _api_error("Facebook Page token validation failed", response)
    payload = response.json()
    resolved_id = str(payload.get("id", "")).strip()
    if resolved_id != page_id:
        raise FacebookPublishError(
            f"Facebook Page token mismatch: expected page {page_id}, got {resolved_id or 'unknown'}."
        )
    return payload


def _verify_published_post(*, post_id: str, page_id: str, page_access_token: str, graph_version: str) -> dict[str, Any]:
    response = requests.get(
        _graph_url(graph_version, post_id),
        headers=_headers(),
        params={
            "fields": "id,from,created_time,is_published,permalink_url,message",
            "access_token": page_access_token,
        },
        timeout=30,
    )
    if not response.ok:
        raise _api_error("Facebook post verification failed", response)
    payload = response.json()
    resolved_id = str(payload.get("id", "")).strip()
    from_data = payload.get("from") or {}
    from_id = str(from_data.get("id", "")).strip() if isinstance(from_data, dict) else ""
    if resolved_id != post_id:
        raise FacebookPublishError(f"Facebook returned a different post ID during verification: {payload}")
    if from_id and from_id != page_id:
        raise FacebookPublishError(
            f"Facebook post owner mismatch: expected page {page_id}, got {from_id}."
        )
    if payload.get("is_published") is False:
        raise FacebookPublishError(f"Facebook accepted the post but reports it is not published: {payload}")
    return payload


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

    try:
        page_identity = _validate_page_token(
            page_id=page_id,
            page_access_token=page_access_token,
            graph_version=graph_version,
        )
        print(f"Facebook page identity verified: {page_identity.get('id')} | {page_identity.get('name', '')}")

        upload_response = requests.post(
            _graph_url(graph_version, page_id, "photos"),
            headers=_headers(),
            data={
                "access_token": page_access_token,
                "published": "false",
            },
            files={"source": (image.name, image.open("rb"), "image/jpeg")},
            timeout=180,
        )
        if not upload_response.ok:
            raise _api_error("Facebook photo upload failed", upload_response)
        upload_payload = upload_response.json()
        photo_id = str(upload_payload.get("id", "")).strip()
        if not photo_id:
            raise FacebookPublishError(f"Facebook returned no unpublished photo ID: {upload_payload}")

        feed_response = requests.post(
            _graph_url(graph_version, page_id, "feed"),
            headers=_headers(),
            data={
                "access_token": page_access_token,
                "message": caption,
                "attached_media[0]": json.dumps({"media_fbid": photo_id}),
            },
            timeout=120,
        )
        if not feed_response.ok:
            raise _api_error("Facebook Page feed publish failed", feed_response)
        feed_payload = feed_response.json()
        post_id = str(feed_payload.get("id", "")).strip()
        if not post_id:
            raise FacebookPublishError(f"Facebook feed publish returned no Post ID: {feed_payload}")

        verification = _verify_published_post(
            post_id=post_id,
            page_id=page_id,
            page_access_token=page_access_token,
            graph_version=graph_version,
        )
        print(
            "Facebook publication verified: "
            f"post_id={post_id} | published={verification.get('is_published')} | "
            f"permalink={verification.get('permalink_url', '')}"
        )
        return {
            "post_id": post_id,
            "photo_id": photo_id,
            "permalink_url": verification.get("permalink_url", ""),
            "verified": True,
            "raw": {"upload": upload_payload, "feed": feed_payload, "verification": verification},
        }
    except requests.RequestException as exc:
        raise FacebookPublishError(f"Facebook publish network error: {exc}") from exc


def like_comment(*, comment_id: str, page_access_token: str, graph_version: str) -> dict[str, Any]:
    comment_id = str(comment_id or "").strip()
    if not comment_id:
        return {"status": "FAILED", "error": "Facebook comment ID is empty."}
    try:
        response = requests.post(
            _graph_url(graph_version, comment_id, "likes"),
            headers=_headers(),
            data={"access_token": page_access_token.strip()},
            timeout=60,
        )
    except requests.RequestException as exc:
        return {"status": "FAILED", "error": str(exc)}
    if not response.ok:
        return {"status": "FAILED", "error": _api_error("Facebook comment like failed", response).args[0]}
    return {"status": "LIKED", "comment_id": comment_id, "raw": response.json()}


def add_comment(*, post_id: str, page_access_token: str, graph_version: str, message: str) -> dict[str, Any]:
    try:
        response = requests.post(
            _graph_url(graph_version, post_id, "comments"),
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
    try:
        response = requests.post(
            _graph_url(graph_version, post_id, "likes"),
            headers=_headers(),
            data={"access_token": page_access_token},
            timeout=60,
        )
    except requests.RequestException as exc:
        return {"status": "FAILED", "error": str(exc)}
    if not response.ok:
        return {"status": "FAILED", "error": _api_error("Facebook like failed", response).args[0]}
    return {"status": "LIKED", "raw": response.json()}
