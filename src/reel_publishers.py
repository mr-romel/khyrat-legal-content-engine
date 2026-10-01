from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import requests

LI_BASE = "https://api.linkedin.com/rest"


def _li_headers(token: str, json_content: bool = False) -> dict[str, str]:
    h = {
        "Authorization": "Bearer " + token,
        "Linkedin-Version": os.getenv("LINKEDIN_VERSION", "202610"),
        "X-Restli-Protocol-Version": "2.0.0",
    }
    if json_content:
        h["Content-Type"] = "application/json"
    return h


def publish_facebook_video(video_path: str, caption: str) -> dict[str, str]:
    page_id = os.getenv("FACEBOOK_PAGE_ID", "").strip()
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
    version = os.getenv("FACEBOOK_GRAPH_VERSION", "26.0").strip().lstrip("v")
    if not page_id or not token:
        raise RuntimeError("Facebook video credentials are incomplete.")
    path = Path(video_path)
    with path.open("rb") as handle:
        response = requests.post(
            f"https://graph.facebook.com/v{version}/{page_id}/videos",
            data={"access_token": token, "description": caption},
            files={"source": (path.name, handle, "video/mp4")},
            timeout=900,
        )
    if not response.ok:
        raise RuntimeError(f"Facebook video publish failed: HTTP {response.status_code} {response.text[:1200]}")
    data = response.json()
    video_id = str(data.get("id", "")).strip()
    if not video_id:
        raise RuntimeError("Facebook returned no video ID.")
    return {"video_id": video_id}


def publish_linkedin_video(video_path: str, commentary: str) -> dict[str, str]:
    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
    author = os.getenv("LINKEDIN_AUTHOR_URN", "").strip()
    if not token:
        raise RuntimeError("LinkedIn access token is missing.")
    if not author:
        from linkedin_publisher import resolve_member_urn
        author = resolve_member_urn(token)

    path = Path(video_path)
    size = path.stat().st_size
    init = requests.post(
        f"{LI_BASE}/videos?action=initializeUpload",
        headers=_li_headers(token, True),
        json={"initializeUploadRequest": {
            "owner": author,
            "fileSizeBytes": size,
            "uploadCaptions": False,
            "uploadThumbnail": False,
        }},
        timeout=120,
    )
    if not init.ok:
        raise RuntimeError(f"LinkedIn video initialization failed: HTTP {init.status_code} {init.text[:1200]}")
    value = init.json().get("value", {})
    video_urn = str(value.get("video", "")).strip()
    instructions = value.get("uploadInstructions") or []
    if not video_urn or not instructions:
        raise RuntimeError("LinkedIn video initialization returned no upload instructions.")

    uploaded_parts = []
    with path.open("rb") as handle:
        for instruction in instructions:
            first = int(instruction["firstByte"])
            last = int(instruction["lastByte"])
            handle.seek(first)
            chunk = handle.read(last - first + 1)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes {first}-{last}/{size}",
            }
            response = requests.put(instruction["uploadUrl"], headers=headers, data=chunk, timeout=900)
            if not response.ok:
                raise RuntimeError(f"LinkedIn video part upload failed: HTTP {response.status_code} {response.text[:1200]}")
            part_id = response.headers.get("etag") or response.headers.get("ETag")
            uploaded_parts.append(part_id or instruction["uploadUrl"])

    finalize = requests.post(
        f"{LI_BASE}/videos?action=finalizeUpload",
        headers=_li_headers(token, True),
        json={"finalizeUploadRequest": {
            "video": video_urn,
            "uploadToken": str(value.get("uploadToken", "")),
            "uploadedPartIds": uploaded_parts,
        }},
        timeout=120,
    )
    if not finalize.ok:
        raise RuntimeError(f"LinkedIn video finalize failed: HTTP {finalize.status_code} {finalize.text[:1200]}")

    post = requests.post(
        f"{LI_BASE}/posts",
        headers=_li_headers(token, True),
        json={
            "author": author,
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "content": {"media": {"title": "Legal educational video", "id": video_urn}},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        },
        timeout=120,
    )
    if not post.ok:
        raise RuntimeError(f"LinkedIn video post failed: HTTP {post.status_code} {post.text[:1200]}")
    post_id = (post.headers.get("x-restli-id") or post.headers.get("X-RestLi-Id") or "").strip()
    if not post_id:
        raise RuntimeError("LinkedIn returned no post ID.")
    return {"video_urn": video_urn, "post_id": post_id}
