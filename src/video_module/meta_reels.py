from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v26.0")


def _request(url: str, fields: dict[str, str]) -> dict:
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode())


def publish_reel(page_id: str, token: str, video: Path, description: str) -> dict[str, str]:
    start = _request(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}/video_reels",
        {"access_token": token, "upload_phase": "start"},
    )
    video_id = str(start["video_id"])
    upload_url = start["upload_url"]
    size = video.stat().st_size
    body = video.read_bytes()
    req = urllib.request.Request(upload_url, data=body, method="POST")
    req.add_header("Authorization", f"OAuth {token}")
    req.add_header("offset", "0")
    req.add_header("file_size", str(size))
    req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req, timeout=180) as response:
        upload = json.loads(response.read().decode())
    if not upload.get("success", True):
        raise RuntimeError(f"META_UPLOAD_FAILED: {upload}")
    finish = _request(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}/video_reels",
        {
            "access_token": token,
            "video_id": video_id,
            "upload_phase": "finish",
            "video_state": "PUBLISHED",
            "description": description,
        },
    )
    if not finish.get("success", True):
        raise RuntimeError(f"META_PUBLISH_FAILED: {finish}")
    return {"video_id": video_id, "post_id": str(finish.get("post_id", ""))}
