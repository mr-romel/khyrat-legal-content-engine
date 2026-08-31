from __future__ import annotations

import json
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


def mark_used(post_id: str) -> None:
    used = load_used()
    used.add(post_id)
    save_used(used)


def choose() -> tuple[PublishedPost, str] | None:
    posts = posts_from_rows(read_rows())
    eligible = [PublishedPost(p.post_id, p.topic, p.content) for p in posts if is_published(p) and p.content and p.image_url]
    post = first_eligible_post(eligible, load_used())
    if post is None:
        return None
    image_url = next(p.image_url for p in posts if p.post_id == post.post_id)
    return post, image_url


def cairo_hour() -> int:
    return datetime.now(ZoneInfo("Africa/Cairo")).hour


def build_once() -> dict[str, str]:
    chosen = choose()
    if chosen is None:
        return {"status": "QUEUE_EMPTY"}
    post, image_url = chosen
    work = Path("video_artifacts")
    script = build_script(post.topic, post.content, max_words=120)
    work.mkdir(parents=True, exist_ok=True)
    (work / "script.txt").write_text(script, encoding="utf-8")
    audio = synthesize_with_fallback(script, work / "voice.mp3", [EdgeTTSProvider(voice="ar-EG-ShakirNeural")])
    captions = caption_from_tts(script, audio, work / "captions.srt")
    image = work / "source.jpg"
    with urlopen(image_url, timeout=30) as response:
        image.write_bytes(response.read())
    logo = Path("generated/ask mahmoud logo.png")
    output = work / "reel_final.mp4"
    render_vertical(image, audio, output, captions, logo if logo.exists() else None)
    validate_mp4(output)
    return {"status": "READY_FOR_META", "post_id": post.post_id, "video": str(output)}
