from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v26.0")


def _request(url: str, fields: dict[str, str]) -> dict:
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw[:1000]}
        raise RuntimeError(f"META_HTTP_{exc.code}: {payload}") from exc


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
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            upload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw[:1000]}
        raise RuntimeError(f"META_UPLOAD_HTTP_{exc.code}: {payload}") from exc
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
