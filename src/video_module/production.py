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
from .script import build_script, _clean
from .sheets_adapter import is_published, posts_from_rows, read_rows
from .selector import first_eligible_post
from .tts import EdgeTTSProvider, LahgtnaChatterboxProvider, synthesize_with_fallback
from .render import render_vertical, validate_mp4
from src.image_generator import create_legal_image, ImageGenerationError

STATE_PATH = Path("video_state/used_posts.json")
PILOT_MAX_CLOUDFLARE_IMAGES = int(os.getenv("VIDEO_PILOT_MAX_CLOUDFLARE_IMAGES", "1"))


def load_used() -> set[str]:
    if not STATE_PATH.exists(): return set()
    try: return set(json.loads(STATE_PATH.read_text(encoding="utf-8")).get("used_post_ids", []))
    except Exception: return set()


def save_used(values: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"used_post_ids": sorted(values)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mark_used(post_id: str) -> None:
    used = load_used(); used.add(post_id); save_used(used)


def choose() -> tuple[PublishedPost, str] | None:
    posts = posts_from_rows(read_rows())
    eligible = [PublishedPost(p.post_id, p.topic, p.content) for p in posts if is_published(p) and p.content and p.image_url]
    post = first_eligible_post(eligible, load_used())
    if post is None: return None
    return post, next(p.image_url for p in posts if p.post_id == post.post_id)


def cairo_hour() -> int:
    return datetime.now(ZoneInfo("Africa/Cairo")).hour


def _pilot_scene_plan(post: PublishedPost) -> list[dict[str, str]]:
    brief = _clean(post.content)[:700]
    return [
        {"image_brief": f"Professional Egyptian legal social-media visual about: {brief}"},
        {"image_brief": f"Clean explanatory legal visual highlighting the key issue: {brief}"},
        {"image_brief": f"Modern courtroom/legal concept visual connected to: {brief}"},
        {"image_brief": f"Simple practical legal advice visual for the audience about: {brief}"},
    ]


def _build_visuals(post: PublishedPost, work: Path, fallback: Path | None = None) -> list[Path]:
    scenes = _pilot_scene_plan(post) if os.getenv("VIDEO_PILOT") == "1" else plan_scenes(post=post.content, count=4)
    visuals: list[Path] = []; generated_count = 0
    for index, scene in enumerate(scenes, start=1):
        output = work / f"scene_{index:02d}.jpg"
        if os.getenv("VIDEO_PILOT") == "1" and generated_count >= PILOT_MAX_CLOUDFLARE_IMAGES:
            if fallback is None: raise ImageGenerationError("VIDEO_PILOT image budget exhausted and no fallback image exists")
            output.write_bytes(fallback.read_bytes()); visuals.append(output); print(f"PILOT_IMAGE_BUDGET_REUSE scene={index}"); continue
        try:
            create_legal_image(topic=post.content, image_brief=scene["image_brief"], output_path=str(output), cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID"), cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN"), page_name="اسأل محمود")
            visuals.append(output); generated_count += 1
        except ImageGenerationError as exc:
            if os.getenv("VIDEO_PILOT") != "1" or fallback is None: raise
            output.write_bytes(fallback.read_bytes()); visuals.append(output); print(f"PILOT_IMAGE_FALLBACK scene={index}: {exc}")
    return visuals


def _pilot_script_fallback(post: PublishedPost) -> str:
    text = _clean(post.content); words = text.split()
    if not words: return ""
    # Never duplicate legal text just to reach an arbitrary word count.
    return " ".join(words[:180]).strip()


def build_once() -> dict[str, str]:
    chosen = choose()
    if chosen is None: return {"status": "QUEUE_EMPTY"}
    post, image_url = chosen; work = Path("video_artifacts"); work.mkdir(parents=True, exist_ok=True)

    if os.getenv("VIDEO_PILOT") == "1":
        script = _pilot_script_fallback(post); print("PILOT_SCRIPT_SOURCE=approved_post_no_gemini")
    else:
        try: script = build_script(post.topic, post.content, max_words=180, post_id=post.post_id)
        except RuntimeError as exc:
            if str(exc) == "GEMINI_QUOTA_EXHAUSTED": return {"status": "GEMINI_QUOTA_EXHAUSTED", "post_id": post.post_id}
            raise

    # Pilot accepts a shorter complete approved post; no artificial repetition.
    if len(script.split()) < 70: raise RuntimeError("VIDEO_SCRIPT_TOO_SHORT")
    (work / "script.txt").write_text(script, encoding="utf-8")

    # Quality-first: Pilot is Egyptian Edge TTS only. It must never silently fall back
    # to the slower/robotic CPU Chatterbox voice. Normal production is untouched.
    if os.getenv("VIDEO_PILOT") == "1":
        audio = EdgeTTSProvider(voice="ar-EG-ShakirNeural").synthesize(script, work / "voice.mp3")
        print("PILOT_TTS_PROVIDER=EdgeTTS"); print("PILOT_TTS_VOICE=ar-EG-ShakirNeural")
    else:
        audio = synthesize_with_fallback(script, work / "voice.mp3", [LahgtnaChatterboxProvider(), EdgeTTSProvider()])

    captions = caption_from_tts(script, audio, work / "captions.srt")
    source = work / "source.jpg"
    with urlopen(image_url, timeout=30) as response: source.write_bytes(response.read())
    generated = _build_visuals(post, work, fallback=source)
    visuals = [source, *generated[:4]]
    logo = Path("generated/ask mahmoud logo.png"); output = work / "reel_final.mp4"
    render_vertical(visuals, audio, output, captions, logo if logo.exists() else None)
    validation = validate_mp4(output)
    return {"status": "READY_FOR_META", "post_id": post.post_id, "video": str(output), "duration": str(validation["duration"])}
