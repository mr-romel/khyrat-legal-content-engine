from __future__ import annotations

# Telegram transport/control module. Reporting implementations live in telegram_reports.py.

import os
from typing import Any

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


def _main_menu_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "📊 تقرير المنصات", "callback_data": "menu:platforms"},
                {"text": "📈 الأداء", "callback_data": "menu:performance"},
            ],
            [
                {"text": "📅 جدول اليوم", "callback_data": "menu:today"},
                {"text": "📝 آخر المنشورات", "callback_data": "menu:recent"},
            ],
            [
                {"text": "🔄 إعادة المحاولة", "callback_data": "menu:retry"},
                {"text": "🩺 فحص النظام", "callback_data": "menu:health"},
            ],
            [
                {"text": "📚 بنك المنشورات", "callback_data": "menu:bank"},
                {"text": "📅 خطة الشهر", "callback_data": "menu:month"},
            ],
            [
                {"text": "🔐 حالة التوكنات", "callback_data": "menu:tokens"},
                {"text": "⚙️ حالة النظام", "callback_data": "menu:system"},
            ],
        ]
    }


def _back_keyboard() -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": "🏠 القائمة الرئيسية", "callback_data": "menu:home"}]]}


def menu_text() -> str:
    return (
        "🤖 KHYRAT LEGAL CONTENT ENGINE\n"
        "Control Center\n\n"
        "اختار العملية من الأزرار — مش محتاج تحفظ أي أمر.\n\n"
        "📢 النشر والتقارير\n"
        "📊 متابعة المنصات والأداء\n"
        "🔧 التحكم والتشخيص\n"
        "📚 المحتوى وخطة الشهر\n"
        "🔐 التوكنات وحالة الخدمات"
    )


def _menu_page(action: str) -> str:
    pages = {
        "platforms": "📊 تقرير المنصات\n\n📘 FACEBOOK — PAGE\n🟢 Publishing\n🟢 Likes\n🟢 Comments\n\n💼 LINKEDIN\n🟢 Publishing\n⚠️ Likes / Comments: راجع آخر LinkedIn Interaction Diagnostic\n\nالتقرير التفصيلي بعد كل نشر هو مصدر الحالة الفعلية.",
        "performance": "📈 الأداء\n\nPerformance Collector يجمع بيانات آخر المنشورات ويحدث بيانات الأداء.\n\nالأرقام التفصيلية تظهر في تقارير الأداء الدورية.",
        "today": "📅 جدول اليوم\n\n🕚 11:00 صباحًا\n🌙 19:00 مساءً\n\nالـScheduler يعمل كل 15 دقيقة، والشيت هو مصدر الحقيقة لموعد كل منشور.",
        "recent": "📝 آخر المنشورات\n\nيتم تسجيل المنشورات ونتائج المنصات في Google Sheets وPost Bank.\n\nالتقرير التفصيلي يظهر تلقائيًا بعد عملية النشر.",
        "retry": "🔄 مركز إعادة المحاولة\n\nالأخطاء المؤقتة القابلة لإعادة المحاولة تدخل Retry Engine تلقائيًا.\n\n⚠️ لا يوجد زر نشر يدوي هنا حاليًا، لتجنب أي نشر مكرر.",
        "health": "🩺 فحص النظام\n\n🟢 Scheduler\n🟢 Google Sheets\n🟢 Gemini + fallback\n🟢 Cloudflare health check\n🟢 Performance Collector\n🟢 Telegram notifications\n\nLinkedIn Interaction تتم متابعته بشكل مستقل.",
        "bank": "📚 بنك المنشورات\n\nالبنك يغذي خطة الشهر بموضوعات غير منشورة مع حماية من التكرار والزوايا المكررة.",
        "month": "📅 خطة الشهر\n\nMonthly Recycler يجهز المواعيد المتبقية ويستخدم موضوعات جديدة من البنك.\n\n🕚 11:00\n🌙 19:00 — بتوقيت القاهرة.",
        "tokens": "🔐 حالة التوكنات\n\nFacebook: Page Access Token\nLinkedIn: Access Token\n\n401 = Token\n403 = Permission / Product Access\n429 و5xx = Temporary / Retry\n\nأي مشكلة فعلية تظهر في التقرير التفصيلي.",
        "system": "⚙️ حالة النظام\n\n🟢 Production Publishing\n🟢 Resilient Scheduler\n🟢 Post Bank\n🟢 Monthly Recycler\n🟢 Performance Collector\n🟢 Telegram Control Center",
    }
    return pages.get(action, menu_text())


def send_control_center(chat_id: str | None = None) -> None:
    target = str(chat_id or _chat_id()).strip()
    if not target:
        return
    _call(
        "sendMessage",
        {
            "chat_id": target,
            "text": menu_text(),
            "reply_markup": _main_menu_keyboard(),
            "disable_web_page_preview": True,
        },
    )


def _authorized(user_id: int | str | None) -> bool:
    expected = _admin_user_id()
    if not expected:
        return True
    return str(user_id or "") == expected


def answer_callback(callback_query_id: str, text: str = "") -> None:
    _call("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text[:190], "show_alert": False})


def edit_menu_message(chat_id: str, message_id: int, action: str) -> None:
    text = menu_text() if action == "home" else _menu_page(action)
    keyboard = _main_menu_keyboard() if action == "home" else _back_keyboard()
    _call(
        "editMessageText",
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "reply_markup": keyboard,
            "disable_web_page_preview": True,
        },
    )


def process_updates_once() -> int:
    """Process pending /start, /menu and Control Center callback updates once."""
    updates = get_updates()
    if not updates:
        return 0
    processed = 0
    for update in updates:
        update_id = int(update.get("update_id", 0))
        message = update.get("message") or {}
        callback = update.get("callback_query") or {}
        user_id = (message.get("from") or {}).get("id") if message else (callback.get("from") or {}).get("id")
        if not _authorized(user_id):
            if callback:
                answer_callback(str(callback.get("id", "")), "غير مصرح")
            continue
        text = str(message.get("text", "")).strip() if message else ""
        if text in {"/start", "/menu", "القائمة", "القائمة الرئيسية"}:
            chat_id = str((message.get("chat") or {}).get("id", _chat_id()))
            send_control_center(chat_id)
            processed += 1
        elif callback:
            data = str(callback.get("data", ""))
            if data.startswith("menu:"):
                action = data.split(":", 1)[1]
                answer_callback(str(callback.get("id", "")))
                callback_message = callback.get("message") or {}
                chat_id = str((callback_message.get("chat") or {}).get("id", ""))
                message_id = int(callback_message.get("message_id", 0))
                if chat_id and message_id:
                    edit_menu_message(chat_id, message_id, action)
                processed += 1
        try:
            get_updates(offset=update_id + 1)
        except Exception as exc:
            print(f"Telegram update acknowledgement failed: {exc}")
    return processed


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


from src.telegram_reports import notify, notify_linkedin_interaction, send_review_request
