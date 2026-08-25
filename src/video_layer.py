from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sheets import get_values, row_to_dict
from telegram_bot import notify, send_message
from utils import now_cairo

VIDEO_TASKS_DIR = Path("generated/video_tasks")
VIDEO_SOURCE_DIR = Path("generated/videos")
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


def _send_video_material(*, topic: str, prompt: str, facebook_post: str) -> None:
    """Send the Prompt and approved Facebook post together in one Telegram message."""
    if not prompt.strip() or not facebook_post.strip():
        return

    message = (
        "🎬 VIDEO MATERIAL — GEMINI NOTEBOOK\n\n"
        f"الموضوع: {topic}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 PROMPT\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{prompt}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📝 APPROVED FACEBOOK POST\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{facebook_post}"
    )
    _send_long_message(message)


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


def build_video_task(*, row_number: int, row: dict[str, str], current) -> Path:
    topic = row.get("الموضوع", "").strip()
    post = row.get("المحتوى", "").strip()
    task_id = _safe_id(row.get("ID", ""), f"row-{row_number}")
    task_path = _task_path(task_id)
    task_path.parent.mkdir(parents=True, exist_ok=True)
    VIDEO_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "task_id": task_id,
        "sheet_row": row_number,
        "topic": topic,
        "duration_target_minutes": VIDEO_MINUTES,
        "language": "Arabic (Colloquial Egyptian)",
        "tool": "Gemini Notebook",
        "status": "AWAITING_MANUAL_VIDEO_CREATION",
        "source_facebook_post": post,
        "prompt": _prompt(topic, post),
        "video_path": str(_video_path(task_id)),
        "created_at": current.isoformat(),
        "telegram_material_sent": False,
    }
    task_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return task_path


def prepare_due_video_tasks(*, service, spreadsheet_id: str, sheet_range: str) -> int:
    """Prepare manual Gemini Notebook material for published posts.

    Video generation, upload, and video publishing are intentionally manual.
    This layer only prepares and sends the approved Facebook post plus its prompt
    to Telegram in one message.
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
            source_post = str(existing.get("source_facebook_post", "")).strip() or post
            try:
                _send_video_material(
                    topic=topic,
                    prompt=prompt,
                    facebook_post=source_post,
                )
                _mark_telegram_material_sent(task_path)
                print(f"Video Layer: sent combined Telegram material for {task_id}.")
                prepared += 1
            except Exception as exc:
                print(f"Video Layer: Telegram resend failed for {task_id}: {exc}")
            continue

        task_path = build_video_task(row_number=row_number, row=row, current=current)

        try:
            notify(
                "🎬 VIDEO LAYER — MANUAL\n\n"
                f"الموضوع: {topic}\n\n"
                "تم تجهيز الـPrompt والبوست المعتمد في رسالة واحدة تالية.\n"
                "إنشاء الفيديو ورفعه ونشره يتم يدويًا بدون الاعتماد على الـAutomation."
            )
            _send_video_material(
                topic=topic,
                prompt=_prompt(topic, post),
                facebook_post=post,
            )
            _mark_telegram_material_sent(task_path)
            prepared += 1
        except Exception as exc:
            print(f"Video Layer: Telegram material delivery failed for {task_id}: {exc}")

    return prepared
