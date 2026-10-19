"""TikTok Content Posting API direct-post client.

This module is deliberately fail-closed. It requires a TikTok developer app approved
for video.publish, user OAuth authorization, and an access token. TikTok may require
additional app review / creator eligibility before posts are public.
Required secrets: TIKTOK_ACCESS_TOKEN
Optional: TIKTOK_PRIVACY_LEVEL (default SELF_ONLY; choose PUBLIC_TO_EVERYONE only
after confirming the app/account is approved for public direct posting).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

API = "https://open.tiktokapis.com/v2"


def publish_tiktok_video(video_path: str, caption: str) -> dict[str, str]:
    token = os.getenv("TIKTOK_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TikTok is not configured: add TIKTOK_ACCESS_TOKEN after TikTok OAuth approval.")
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"TikTok upload video not found: {path}")
    size = path.stat().st_size
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    init = requests.post(
        f"{API}/post/publish/video/init/",
        headers=headers,
        json={
            "post_info": {
                "title": (caption or "").strip()[:2200],
                "privacy_level": os.getenv("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY").strip(),
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": min(size, 10 * 1024 * 1024),
                "total_chunk_count": (size + min(size, 10 * 1024 * 1024) - 1) // min(size, 10 * 1024 * 1024),
            },
        },
        timeout=60,
    )
    if not init.ok:
        raise RuntimeError(f"TikTok upload initialization failed: HTTP {init.status_code} {init.text[:900]}")
    payload = init.json()
    if payload.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok upload initialization rejected: {payload['error']}")
    data = payload.get("data") or {}
    upload_url = data.get("upload_url")
    publish_id = data.get("publish_id")
    if not upload_url or not publish_id:
        raise RuntimeError("TikTok did not return upload_url and publish_id.")

    chunk_size = min(size, 10 * 1024 * 1024)
    with path.open("rb") as stream:
        start = 0
        while start < size:
            chunk = stream.read(chunk_size)
            end = start + len(chunk) - 1
            response = requests.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {start}-{end}/{size}",
                    "Content-Length": str(len(chunk)),
                },
                data=chunk,
                timeout=300,
            )
            if response.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok chunk upload failed: HTTP {response.status_code} {response.text[:600]}")
            start = end + 1

    # Return the publish ID; the workflow can query status separately.
    return {"publish_id": str(publish_id), "status": "PROCESSING"}
