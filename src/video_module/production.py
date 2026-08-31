from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from .captions import caption_from_tts
from .models import PublishedPost
from .script import build_script
from .sheets_adapter import is_published, posts_from_rows, read_rows
from .selector import first_eligible_post
from .tts import EdgeTTSProvider, synthesize_with_fallback
from .render import render_vertical, validate_mp4

STATE_PATH = Path("video_state/used_posts.json")


def load_used() -> set[str]:
    if not STATE_PATH.exists():
        return set()
    try:
        return set(json.loads(STATE_PATH.read_text(encoding="utf-8")).get("used_post_ids", []))
    except Exception:
        return set()


def save_used(values: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"used_post_ids": sorted(values)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def choose() -> PublishedPost | None:
    posts = posts_from_rows(read_rows())
    eligible = []
    for p in posts:
        if is_published(p) and p.content and p.image_url:
            eligible.append(PublishedPost(p.post_id, p.topic, p.content))
    return first_eligible_post(eligible, load_used())


def download(url: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=30) as r:
        path.write_bytes(r.read())
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("image download failed")
    return path


def cairo_hour() -> int:
    return datetime.now(ZoneInfo("Africa/Cairo")).hour


def build_once(public_video_url: str) -> dict[str, str]:
    post = choose()
    if post is None:
        return {"status": "QUEUE_EMPTY"}
    work = Path("video_artifacts")
    script = build_script(post.topic, post.content, max_words=120)
    script_path = work / "script.txt"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script, encoding="utf-8")
    audio = synthesize_with_fallback(script, work / "voice.mp3", [EdgeTTSProvider()])
    captions = caption_from_tts(script, audio, work / "captions.srt")
    image_url = next(p.image_url for p in posts_from_rows(read_rows()) if p.post_id == post.post_id)
    image = download(image_url, work / "source.jpg")
    logo = Path("generated/ask mahmoud logo.png")
    output = work / "reel_final.mp4"
    render_vertical(image, audio, output, captions, logo if logo.exists() else None)
    validate_mp4(output)
    if not public_video_url:
        raise RuntimeError("VIDEO_PILOT_PUBLIC_URL is required")
    used = load_used()
    used.add(post.post_id)
    save_used(used)
    return {"status": "READY_FOR_META", "post_id": post.post_id, "video": str(output), "public_url": public_video_url}
