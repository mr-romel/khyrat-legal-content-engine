from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from .captions import caption_from_tts
from .models import PublishedPost
from .scene_planner import plan_scenes
from .script import build_script
from .sheets_adapter import is_published, posts_from_rows, read_rows
from .selector import first_eligible_post
from .tts import EdgeTTSProvider, LahgtnaChatterboxProvider, synthesize_with_fallback
from .render import render_vertical, validate_mp4
from src.image_generator import create_legal_image, ImageGenerationError

STATE_PATH = Path("video_state/used_posts.json")

# The isolated pilot is deliberately quota-safe. One Cloudflare generation is
# enough to prove the complete visual/render path; the remaining scenes reuse
# the approved source image. This prevents repeated pilot runs from consuming
# the production account's daily Workers AI allocation.
PILOT_MAX_CLOUDFLARE_IMAGES = int(os.getenv("VIDEO_PILOT_MAX_CLOUDFLARE_IMAGES", "1"))


def load_used() -> set[str]:
    if not STATE_PATH.exists():
        return set()
    try:
        return set(json.loads(STATE_PATH.read_text(encoding="utf-8")).get("used_post_ids", []))
    except Exception:
        return set()


def save_used(values: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"used_post_ids": sorted(values)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def mark_used(post_id: str) -> None:
    used = load_used()
    used.add(post_id)
    save_used(used)


def choose() -> tuple[PublishedPost, str] | None:
    posts = posts_from_rows(read_rows())
    eligible = [
        PublishedPost(p.post_id, p.topic, p.content)
        for p in posts
        if is_published(p) and p.content and p.image_url
    ]
    post = first_eligible_post(eligible, load_used())
    if post is None:
        return None
    image_url = next(p.image_url for p in posts if p.post_id == post.post_id)
    return post, image_url


def cairo_hour() -> int:
    return datetime.now(ZoneInfo("Africa/Cairo")).hour


def _build_visuals(post: PublishedPost, work: Path, fallback: Path | None = None) -> list[Path]:
    scenes = plan_scenes(post=post.content, count=4)
    visuals: list[Path] = []
    generated_count = 0
    for index, scene in enumerate(scenes, start=1):
        output = work / f"scene_{index:02d}.jpg"

        # In the isolated pilot, generate at most one fresh visual. Reusing the
        # approved source for later scenes still exercises scene planning,
        # captioning, rendering and MP4 validation without burning the daily
        # Cloudflare AI allocation on four near-identical test generations.
        if os.getenv("VIDEO_PILOT") == "1" and generated_count >= PILOT_MAX_CLOUDFLARE_IMAGES:
            if fallback is None:
                raise ImageGenerationError("VIDEO_PILOT image budget exhausted and no fallback image exists")
            print(f"PILOT_IMAGE_BUDGET_REUSE scene={index}: using approved source image")
            visuals.append(fallback)
            continue

        try:
            create_legal_image(
                topic=post.content,
                image_brief=scene["image_brief"],
                output_path=str(output),
                cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID"),
                cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN"),
                page_name="اسأل محمود",
            )
            visuals.append(output)
            generated_count += 1
        except ImageGenerationError as exc:
            if os.getenv("VIDEO_PILOT") != "1" or fallback is None:
                raise
            print(f"PILOT_IMAGE_FALLBACK scene={index}: {exc}")
            visuals.append(fallback)
    return visuals


def build_once() -> dict[str, str]:
    chosen = choose()
    if chosen is None:
        return {"status": "QUEUE_EMPTY"}
    post, image_url = chosen
    work = Path("video_artifacts")
    work.mkdir(parents=True, exist_ok=True)

    try:
        script = build_script(post.topic, post.content, max_words=180, post_id=post.post_id)
    except RuntimeError as exc:
        if str(exc) == "GEMINI_QUOTA_EXHAUSTED":
            return {"status": "GEMINI_QUOTA_EXHAUSTED", "post_id": post.post_id}
        raise

    (work / "script.txt").write_text(script, encoding="utf-8")
    audio = synthesize_with_fallback(
        script,
        work / "voice.mp3",
        [LahgtnaChatterboxProvider(), EdgeTTSProvider()],
    )
    captions = caption_from_tts(script, audio, work / "captions.srt")
    source = work / "source.jpg"
    with urlopen(image_url, timeout=30) as response:
        source.write_bytes(response.read())
    generated = _build_visuals(post, work, fallback=source)
    visuals = [source, *generated[:4]]
    logo = Path("generated/ask mahmoud logo.png")
    output = work / "reel_final.mp4"
    render_vertical(visuals, audio, output, captions, logo if logo.exists() else None)
    validation = validate_mp4(output)
    return {
        "status": "READY_FOR_META",
        "post_id": post.post_id,
        "video": str(output),
        "duration": str(validation["duration"]),
    }
