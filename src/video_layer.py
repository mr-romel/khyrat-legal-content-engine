from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sheets import get_values, row_to_dict
from telegram_bot import send_message
from utils import now_cairo

VIDEO_TASKS_DIR = Path("generated/video_tasks")
VIDEO_DURATION = "45–75 seconds"
TELEGRAM_SAFE_LIMIT = 3900


def _safe_id(value: str, fallback: str) -> str:
    raw = (value or fallback).strip()
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in raw)
    return safe or fallback


def _published(row: dict[str, str]) -> bool:
    status = row.get("الحالة", "").strip().upper()
    fb = row.get("Facebook Status", "").strip().upper()
    li = row.get("LinkedIn Status", "").strip().upper()
    return status == "PUBLISHED" or fb == "PUBLISHED" or li == "PUBLISHED"


def _prompt(topic: str, facebook_post: str) -> str:
    return f"""Create a 9:16 vertical legal Reel / Short, {VIDEO_DURATION}, based ONLY on the approved Facebook post below.

Language: natural Egyptian Arabic. Audience: Egyptian non-lawyers. Start with a strong hook, explain simply and quickly, then end with a practical takeaway/CTA supported by the source. Use a confident, calm, natural Egyptian male lawyer voice (late 30s), not a news presenter. Use clean legal/social visuals, simple transitions, and short large on-screen text for key points only. No music or distracting sound effects. No lawyer avatar required. Maintain the “اسأل محمود” identity.

LEGAL SAFETY: The approved post is the sole legal source. Do not add or invent any article, ruling, penalty, deadline, exception, fact, example, statistic, legal conclusion, or other information. Do not change the legal meaning. Do not add disclaimers or filler. Output VIDEO ONLY: no caption, description, title, hashtags, or separate publishing text.

TOPIC: {topic}

APPROVED FACEBOOK POST — USE IT AS THE SOLE SOURCE:
{facebook_post}

FINAL: Produce the short-form 9:16 Reel / Short itself and nothing else."""


def _task_path(task_id: str) -> Path:
    return VIDEO_TASKS_DIR / f"{task_id}.json"


def _load_task(task_path: Path) -> dict[str, Any] | None:
    if not task_path.is_file():
        return None
    try:
        return json.loads(task_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Video Layer: could not read task {task_path}: {exc}")
        return None


def _mark_telegram_material_sent(task_path: Path) -> None:
    payload = _load_task(task_path) or {}
    payload["telegram_material_sent"] = True
    payload["telegram_material_sent_at"] = now_cairo().isoformat()
    task_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _send_video_material(*, topic: str, prompt: str) -> None:
    """Send the complete, compact Notebook prompt in one Telegram message whenever possible."""
    if not prompt.strip():
        return
    message = f"🎬 VIDEO MATERIAL — GEMINI NOTEBOOK\n\nالموضوع: {topic}\n\n{prompt}"
    if len(message) > TELEGRAM_SAFE_LIMIT:
        raise ValueError(f"Video Telegram material exceeds safe single-message limit: {len(message)} chars")
    send_message(message)


def build_video_task(*, row_number: int, row: dict[str, str], current) -> Path:
    topic = row.get("الموضوع", "").strip()
    post = row.get("المحتوى", "").strip()
    task_id = _safe_id(row.get("ID", ""), f"row-{row_number}")
    task_path = _task_path(task_id)
    task_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "task_id": task_id,
        "sheet_row": row_number,
        "topic": topic,
        "duration_target": VIDEO_DURATION,
        "format": "9:16 vertical Reel / Short",
        "language": "Arabic (Colloquial Egyptian)",
        "tool": "Gemini Notebook",
        "status": "AWAITING_MANUAL_VIDEO_CREATION",
        "source_facebook_post": post,
        "prompt": _prompt(topic, post),
        "created_at": current.isoformat(),
        "telegram_material_sent": False,
    }
    task_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return task_path


def prepare_due_video_tasks(*, service, spreadsheet_id: str, sheet_range: str) -> int:
    """Prepare manual Gemini Notebook Reel material for published posts.

    Video creation, upload, publishing, captions, and descriptions remain manual.
    Each eligible post gets one compact Telegram message containing the full prompt,
    with the approved Facebook post embedded once inside it.
    """
    current = now_cairo()
    values = get_values(service, spreadsheet_id, sheet_range)
    if not values:
        return 0

    prepared = 0
    for row_number, raw in enumerate(values[1:], start=2):
        row = row_to_dict(raw)
        if not _published(row):
            continue

        topic = row.get("الموضوع", "").strip()
        post = row.get("المحتوى", "").strip()
        if not topic or not post:
            continue

        task_id = _safe_id(row.get("ID", ""), f"row-{row_number}")
        task_path = _task_path(task_id)
        existing = _load_task(task_path)

        if existing and existing.get("telegram_material_sent") is True:
            continue

        if existing:
            prompt = str(existing.get("prompt", "")).strip() or _prompt(topic, post)
            try:
                _send_video_material(topic=topic, prompt=prompt)
                _mark_telegram_material_sent(task_path)
                print(f"Video Layer: sent compact Telegram Reel prompt for {task_id}.")
                prepared += 1
            except Exception as exc:
                print(f"Video Layer: Telegram resend failed for {task_id}: {exc}")
            continue

        task_path = build_video_task(row_number=row_number, row=row, current=current)
        try:
            _send_video_material(topic=topic, prompt=_prompt(topic, post))
            _mark_telegram_material_sent(task_path)
            prepared += 1
        except Exception as exc:
            print(f"Video Layer: Telegram Reel prompt delivery failed for {task_id}: {exc}")

    return prepared
