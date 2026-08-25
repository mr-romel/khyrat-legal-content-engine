from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sheets import get_values, row_to_dict
from telegram_bot import notify, send_message
from utils import now_cairo, parse_date, parse_time

VIDEO_TASKS_DIR = Path("generated/video_tasks")
VIDEO_SOURCE_DIR = Path("generated/videos")
VIDEO_DELAY_HOURS = 2
VIDEO_MINUTES = "1–3"
GITHUB_TASK_URL = "https://github.com/mr-romel/khyrat-legal-content-engine/blob/main/"
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


def _written_publish_at(row: dict[str, str]) -> datetime | None:
    target_date = parse_date(row.get("تاريخ النشر", ""))
    target_time = parse_time(row.get("ساعة النشر", ""))
    if target_date is None or target_time is None:
        return None
    current = now_cairo()
    return current.replace(
        year=target_date.year,
        month=target_date.month,
        day=target_date.day,
        hour=target_time.hour,
        minute=target_time.minute,
        second=0,
        microsecond=0,
    )


def _prompt(topic: str, facebook_post: str) -> str:
    return f"""Create an Egyptian Arabic explainer video based STRICTLY on the approved Facebook post below.

Target duration: {VIDEO_MINUTES} minutes.
Language: Arabic (Colloquial Egyptian).
Format: Explainer / educational social video.
Audience: Egyptian non-lawyers who need a clear practical understanding.
Narration style: confident, calm, professional Egyptian legal expert in his late thirties; natural and conversational, not theatrical, not a news presenter, and not overly academic.
Structure: strong opening hook, explain the legal point simply, give a short practical example when supported by the source, then finish with a concise takeaway.
Visuals: clean, modern legal/social-media explainer visuals. No requirement for an on-screen lawyer avatar.

LEGAL SAFETY RULES:
- Treat the Facebook post below as the controlling source.
- Do NOT add any legal rule, article number, court ruling, penalty, deadline, exception, or factual claim that is not supported by the source.
- Do NOT invent facts or examples that could change the legal meaning.
- If a sentence is too technical for spoken explanation, simplify its language without changing its legal meaning.
- Do not turn the video into a legal disclaimer or a long lecture.
- Keep the explanation engaging and easy to follow.

TOPIC:
{topic}

APPROVED FACEBOOK POST:
{facebook_post}
"""


def _task_path(task_id: str) -> Path:
    return VIDEO_TASKS_DIR / f"{task_id}.json"


def _video_path(task_id: str) -> Path:
    return VIDEO_SOURCE_DIR / f"{task_id}.mp4"


def _send_video_material(*, topic: str, video_at: datetime, prompt: str, facebook_post: str, task_url: str, video_file: Path) -> None:
    """Send the complete Notebook input to Telegram without truncating the source post/prompt."""
    if not prompt.strip() or not facebook_post.strip():
        return

    send_message(
        "🎬 VIDEO LAYER — Gemini Notebook\n\n"
        f"الموضوع: {topic}\n"
        f"موعد الريلز المستهدف: {video_at.strftime('%Y-%m-%d %H:%M')} بتوقيت القاهرة\n\n"
        "دورك الآن:\n"
        "1) استخدم الـPrompt والـFacebook Post الموجودين في الرسالتين التاليتين.\n"
        "2) افتح Gemini Notebook.\n"
        "3) اختر Video Overview → Explainer → Arabic (Colloquial Egyptian).\n"
        "4) ولّد الفيديو واستهدف مدة 1–3 دقائق.\n"
        "5) نزّل ملف MP4.\n"
        f"6) ارفع الملف إلى: {video_file.as_posix()}\n\n"
        f"📄 ملف المهمة على GitHub: {task_url}"
    )

    _send_long_message("🧠 GEMINI NOTEBOOK — PROMPT\n\n" + prompt)
    _send_long_message("📝 GEMINI NOTEBOOK — APPROVED FACEBOOK POST\n\n" + facebook_post)


def _send_long_message(text: str) -> None:
    """Split Telegram messages safely below Telegram's message-size limit."""
    remaining = text
    while remaining:
        chunk = remaining[:TELEGRAM_SAFE_LIMIT]
        if len(remaining) > TELEGRAM_SAFE_LIMIT:
            split_at = chunk.rfind("\n")
            if split_at > 500:
                chunk = chunk[:split_at]
        send_message(chunk)
        remaining = remaining[len(chunk):]


def build_video_task(*, row_number: int, row: dict[str, str], current: datetime) -> Path:
    topic = row.get("الموضوع", "").strip()
    post = row.get("المحتوى", "").strip()
    task_id = _safe_id(row.get("ID", ""), f"row-{row_number}")
    task_path = _task_path(task_id)
    task_path.parent.mkdir(parents=True, exist_ok=True)
    VIDEO_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    written_at = _written_publish_at(row) or current
    video_at = written_at + timedelta(hours=VIDEO_DELAY_HOURS)
    payload: dict[str, Any] = {
        "task_id": task_id,
        "sheet_row": row_number,
        "topic": topic,
        "written_publish_at": written_at.isoformat(),
        "video_publish_at": video_at.isoformat(),
        "duration_target_minutes": VIDEO_MINUTES,
        "language": "Arabic (Colloquial Egyptian)",
        "tool": "Gemini Notebook",
        "status": "AWAITING_GEMINI_NOTEBOOK",
        "source_facebook_post": post,
        "prompt": _prompt(topic, post),
        "video_path": str(_video_path(task_id)),
        "created_at": current.isoformat(),
    }
    task_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return task_path


def prepare_due_video_tasks(*, service, spreadsheet_id: str, sheet_range: str) -> int:
    """Prepare one Gemini Notebook task for each eligible published post.

    Gemini Notebook currently has no public Video Overview generation API in our verified
    integration surface, so this layer prepares the exact source/prompt and alerts the owner.
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
        written_at = _written_publish_at(row)
        if written_at is None:
            continue
        video_at = written_at + timedelta(hours=VIDEO_DELAY_HOURS)
        if current < video_at:
            continue

        task_id = _safe_id(row.get("ID", ""), f"row-{row_number}")
        task_path = _task_path(task_id)
        if task_path.exists():
            continue

        task_path = build_video_task(row_number=row_number, row=row, current=current)
        video_file = _video_path(task_id)
        task_url = f"{GITHUB_TASK_URL}{task_path.as_posix()}"

        # Keep the concise notification, then send the exact Prompt and approved post
        # in separate Telegram messages so the user can copy them directly into Gemini Notebook.
        notify(
            "🎬 VIDEO LAYER — Gemini Notebook\n\n"
            f"الموضوع: {topic}\n"
            f"موعد الريلز المستهدف: {video_at.strftime('%Y-%m-%d %H:%M')} بتوقيت القاهرة\n\n"
            "تم تجهيز الـPrompt والبوست المعتمد في الرسالتين التاليتين.\n"
            "بعد التوليد: نزّل MP4 ثم ارفعه للمسار المحدد.\n\n"
            f"📄 Video Task: {task_url}"
        )
        _send_video_material(
            topic=topic,
            video_at=video_at,
            prompt=_prompt(topic, post),
            facebook_post=post,
            task_url=task_url,
            video_file=video_file,
        )
        prepared += 1

    return prepared
