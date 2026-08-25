from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sheets import get_values, row_to_dict
from telegram_bot import notify
from utils import now_cairo, parse_date, parse_time

VIDEO_TASKS_DIR = Path("generated/video_tasks")
VIDEO_SOURCE_DIR = Path("generated/videos")
VIDEO_DELAY_HOURS = 2
VIDEO_MINUTES = "1–3"
GITHUB_TASK_URL = "https://github.com/mr-romel/khyrat-legal-content-engine/blob/main/"


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
        notify(
            "🎬 VIDEO LAYER — Gemini Notebook\n\n"
            f"الموضوع: {topic}\n"
            f"موعد الريلز المستهدف: {video_at.strftime('%Y-%m-%d %H:%M')} بتوقيت القاهرة\n\n"
            "دورك الآن:\n"
            "1) افتح ملف مهمة الفيديو من الزر/الرابط.\n"
            "2) انسخ الـAPPROVED FACEBOOK POST والـPrompt إلى Gemini Notebook.\n"
            "3) اختر Video Overview → Explainer → Arabic (Colloquial Egyptian).\n"
            "4) ولّد الفيديو واستهدف مدة 1–3 دقائق.\n"
            "5) نزّل ملف MP4.\n"
            f"6) ارفع الملف إلى: {video_file.as_posix()}\n\n"
            f"📄 Video Task: {task_url}\n\n"
            "بعد رفع الـMP4 نقدر نكمل مرحلة النشر الآلي كمرحلة مستقلة."
        )
        prepared += 1

    return prepared
