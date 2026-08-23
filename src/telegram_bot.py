from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests


class TelegramError(RuntimeError):
    pass


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "").strip()


def _admin_user_id() -> str:
    return os.getenv("TELEGRAM_ADMIN_USER_ID", "").strip()


def _call(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = _token()
    if not token:
        raise TelegramError("TELEGRAM_BOT_TOKEN is missing.")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/{method}",
        json=payload,
        timeout=30,
    )
    try:
        data = response.json()
    except ValueError:
        raise TelegramError(f"Telegram returned invalid JSON: {response.text[:500]}")
    if not response.ok or not data.get("ok"):
        raise TelegramError(f"Telegram {method} failed: {data}")
    return data


def configured() -> bool:
    return bool(_token() and _chat_id())


def send_message(text: str, *, reply_markup: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not configured():
        return None
    payload: dict[str, Any] = {
        "chat_id": _chat_id(),
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _call("sendMessage", payload).get("result")


def send_review_request(*, row_number: int, topic: str, post: str, reason: str, sheet_id: str, status: str) -> None:
    if not configured():
        print("Telegram not configured; review notification skipped.")
        return
    sheet_url = f"https://docs.google.com/spreadsheets/d/{quote(sheet_id, safe='')}/edit"
    text = (
        "🚨 Khyrat Legal Content Engine\n\n"
        f"الحالة: {status}\n"
        f"الصف: {row_number}\n"
        f"الموضوع: {topic}\n\n"
        f"سبب المراجعة:\n{reason or 'يحتاج مراجعة قانونية.'}\n\n"
        f"محتوى المنشور:\n{post[:3500]}\n\n"
        "الخطوات:\n"
        "1) افتح المحتوى من الزر.\n"
        "2) راجع النص والمصادر.\n"
        "3) اختر موافقة أو رفض.\n"
        "4) الموافقة تسمح بنشر هذا البوست فقط؛ باقي الأتمتة تستمر طبيعيًا."
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ موافقة ونشر", "callback_data": f"approve:{row_number}"},
                {"text": "❌ رفض", "callback_data": f"reject:{row_number}"},
            ],
            [{"text": "📊 فتح Google Sheet", "url": sheet_url}],
        ]
    }
    send_message(text, reply_markup=keyboard)


def notify(text: str) -> None:
    try:
        send_message(text)
    except Exception as exc:
        print(f"Telegram notification failed: {exc}")


def notify_linkedin_interaction(*, topic: str, post_urn: str, comment: dict[str, Any], like: dict[str, Any]) -> None:
    """Send a compact diagnostic report for LinkedIn like/comment actions."""
    if not configured():
        return

    def render(label: str, result: dict[str, Any], success_labels: set[str]) -> str:
        status = str(result.get("status", "UNKNOWN"))
        http_status = result.get("http_status")
        error = str(result.get("error", "")).strip()
        if status in success_labels:
            return f"{label}: ✅ {status}"
        line = f"{label}: ❌ {status}"
        if http_status:
            line += f" (HTTP {http_status})"
        if error:
            line += f"\n   السبب: {error[:700]}"
        return line

    text = (
        "💼 LinkedIn Interaction Diagnostic\n\n"
        f"الموضوع: {topic}\n"
        f"Post URN: {post_urn}\n\n"
        f"{render('❤️ Like', like, {'LIKED'})}\n"
        f"{render('💬 Comment', comment, {'PUBLISHED'})}\n\n"
        "النشر الأساسي لا يتأثر بفشل التفاعل. "
        "لو ظهر 401/403 هنا، نعرف أن المشكلة في التوكن/الصلاحيات وليس في الـScheduler."
    )
    notify(text)


def answer_callback(callback_query_id: str, text: str) -> None:
    _call("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text, "show_alert": False})


def edit_message(chat_id: str, message_id: int, text: str) -> None:
    _call("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text})


def get_updates(offset: int | None = None) -> list[dict[str, Any]]:
    if not _token():
        return []
    payload: dict[str, Any] = {"limit": 100, "timeout": 0, "allowed_updates": ["callback_query", "message"]}
    if offset is not None:
        payload["offset"] = offset
    return _call("getUpdates", payload).get("result", [])


def authorized_user(user_id: int | str) -> bool:
    expected = _admin_user_id()
    return bool(expected and str(user_id) == expected)
