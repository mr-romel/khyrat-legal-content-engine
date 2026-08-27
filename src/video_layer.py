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
    return f"""Create a short-form vertical legal Reel / Short for social media based STRICTLY on the approved Facebook post below.

TARGET FORMAT:
- Duration: {VIDEO_DURATION}.
- Aspect ratio: 9:16 vertical, optimized for mobile screens.
- Platform style: Instagram Reels / Facebook Reels / YouTube Shorts.
- Language: natural, clear Egyptian Arabic (Colloquial Egyptian).
- Audience: Egyptian non-lawyers who need a quick, practical understanding.
- Output: create the VIDEO ONLY. Do not create a caption, description, post copy, title, hashtags, or separate social-media text.

PRESENTATION:
- Open with a strong, attention-grabbing hook in the first seconds.
- Explain the legal point quickly and simply.
- Keep the pacing energetic enough for a Reel / Short without becoming theatrical.
- End with a concise practical takeaway or natural call to action supported by the source.
- Do not turn the video into a lecture, formal legal memo, or generic explainer.
- Use a confident, calm, professional Egyptian male lawyer voice in his late thirties; natural and conversational, trustworthy and reassuring, not a news presenter and not overly academic.

VISUAL DIRECTION:
- Use clean, modern legal/social-media visuals appropriate for a short-form Reel.
- Suggest or create simple relevant scenes and transitions that support the spoken content.
- Use short, large, mobile-readable on-screen text only for key points; do not put the full narration on screen.
- Keep the visual composition clean and uncluttered.
- Voice must remain the primary element; do not use music or sound effects that compete with the narration.
- No requirement for an on-screen lawyer avatar.
- Maintain the professional identity of “اسأل محمود” without adding personal information or names not contained in the source.

LEGAL SAFETY — STRICT:
- The approved Facebook post below is the ONLY controlling legal source.
- Do NOT add any legal rule, article number, court ruling, penalty, deadline, exception, factual claim, or legal conclusion that is not supported by the approved post.
- Do NOT invent facts, examples, scenarios, statistics, or details that could change the legal meaning.
- Do NOT alter the legal result while simplifying the language for spoken Egyptian Arabic.
- If a technical term is necessary, explain it simply without changing its meaning.
- Do not add a legal disclaimer or filler that distracts from the content.
- Do not generate a caption, description, hashtags, or any separate publishing copy.

TOPIC:
{topic}

APPROVED FACEBOOK POST — USE THIS CONTENT AS THE SOLE SOURCE FOR THE VIDEO:
{facebook_post}

FINAL INSTRUCTION:
Produce the short-form 9:16 Reel / Short itself. Do not output or generate any caption, description, hashtags, or separate post text. Do not introduce information beyond the approved Facebook post above."""


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
    """Send one Telegram message with one prompt containing the approved post once."""
    if not prompt.strip():
        return

    message = (
        "🎬 VIDEO MATERIAL — GEMINI NOTEBOOK\n\n"
        f"الموضوع: {topic}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 PROMPT\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{prompt}"
    )
    _send_long_message(message)


def _send_long_message(text: str) -> None:
    """Split only when Telegram's hard message-size limit requires it."""
    remaining = text
    while remaining:
        chunk = remaining[:TELEGRAM_SAFE_LIMIT]
        if len(remaining) > TELEGRAM_SAFE_LIMIT:
            split_at = chunk.rfind("\n")
            if split_at > 500:
                chunk = chunk[:split_at]
        send_message(chunk)
        remaining = remaining[len(chunk):]


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

    Video creation, upload, publishing, captions, and descriptions are intentionally manual.
    This layer only sends one Telegram message containing the prompt and the approved
    Facebook post embedded once inside that prompt.
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
                print(f"Video Layer: sent combined Telegram Reel prompt for {task_id}.")
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
