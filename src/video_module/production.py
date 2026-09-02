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
from .script import build_pilot_script, build_script
from .sheets_adapter import is_published, posts_from_rows, read_rows
from .selector import first_eligible_post
from .tts import EdgeTTSProvider, LahgtnaChatterboxProvider, synthesize_with_fallback
from .render import render_vertical, validate_mp4
from .whiteboard import write_whiteboard_scenes
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


def _build_normal_visuals(post: PublishedPost, work: Path, fallback: Path | None = None) -> list[Path]:
    scenes = plan_scenes(post=post.content, count=4)
    visuals: list[Path] = []
    for index, scene in enumerate(scenes, start=1):
        output = work / f"scene_{index:02d}.jpg"
        try:
            create_legal_image(topic=post.content, image_brief=scene["image_brief"], output_path=str(output), cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID"), cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN"), page_name="اسأل محمود")
            visuals.append(output)
        except ImageGenerationError:
            if fallback is None: raise
            output.write_bytes(fallback.read_bytes()); visuals.append(output)
    return visuals


def build_once() -> dict[str, str]:
    chosen = choose()
    if chosen is None: return {"status": "QUEUE_EMPTY"}
    post, image_url = chosen
    work = Path("video_artifacts")
    work.mkdir(parents=True, exist_ok=True)

    if os.getenv("VIDEO_PILOT") == "1":
        # The pilot must synthesize the actual spoken script, not the formal post.
        # This is what makes the TTS pronunciation Egyptian instead of merely
        # changing a few words after generation.
        script = build_pilot_script(post.topic, post.content, post_id=post.post_id)
        print("PILOT_SCRIPT_SOURCE=gemini_egyptian_colloquial")
    else:
        try:
            script = build_script(post.topic, post.content, max_words=180, post_id=post.post_id)
        except RuntimeError as exc:
            if str(exc) == "GEMINI_QUOTA_EXHAUSTED": return {"status": "GEMINI_QUOTA_EXHAUSTED", "post_id": post.post_id}
            raise

    if len(script.split()) < 70:
        raise RuntimeError("VIDEO_SCRIPT_TOO_SHORT")
    (work / "script.txt").write_text(script, encoding="utf-8")

    if os.getenv("VIDEO_PILOT") == "1":
        # Use the Egyptian Chatterbox/Lahgtna provider again. Edge TTS is not the
        # pilot voice because its delivery was judged too synthetic. A reference
        # clip can be supplied through VIDEO_PILOT_EGYPTIAN_REF_AUDIO when a
        # specific youthful male timbre is desired; otherwise the model uses its
        # native Egyptian voice conditioning.
        audio = LahgtnaChatterboxProvider().synthesize(script, work / "voice.mp3")
        print("PILOT_TTS_PROVIDER=LahgtnaChatterbox")
        print("PILOT_TTS_DIALECT=Egyptian_Arabic")
        print("PILOT_TTS_STYLE=young_confident_clear")
        print(f"PILOT_TTS_REFERENCE={'configured' if os.getenv('VIDEO_PILOT_EGYPTIAN_REF_AUDIO', '').strip() else 'native_egyptian'}")
    else:
        audio = synthesize_with_fallback(script, work / "voice.mp3", [LahgtnaChatterboxProvider(), EdgeTTSProvider()])

    captions = caption_from_tts(script, audio, work / "captions.srt")
    if os.getenv("VIDEO_PILOT") == "1":
        visuals = write_whiteboard_scenes(work / "whiteboard", topic=post.topic, content=post.content, count=5)
        print(f"PILOT_VISUAL_STYLE=animated_whiteboard_action SCENES={len(visuals)}")
    else:
        source = work / "source.jpg"
        with urlopen(image_url, timeout=30) as response: source.write_bytes(response.read())
        visuals = [source, *_build_normal_visuals(post, work, fallback=source)][:5]
    logo = Path("generated/ask mahmoud logo.png")
    output = work / "reel_final.mp4"
    render_vertical(visuals, audio, output, captions, logo if logo.exists() else None, animated=os.getenv("VIDEO_PILOT") == "1")
    validation = validate_mp4(output)
    return {"status": "READY_FOR_META", "post_id": post.post_id, "video": str(output), "duration": str(validation["duration"])}
