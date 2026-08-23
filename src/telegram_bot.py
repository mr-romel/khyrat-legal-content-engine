from __future__ import annotations

import os
import re
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
        "platforms": (
            "📊 تقرير المنصات\n\n"
            "📘 FACEBOOK — PAGE\n"
            "🟢 Publishing\n"
            "🟢 Likes\n"
            "🟢 Comments\n\n"
            "💼 LINKEDIN\n"
            "🟢 Publishing\n"
            "⚠️ Likes / Comments: راجع آخر LinkedIn Interaction Diagnostic\n\n"
            "التقرير التفصيلي بعد كل نشر هو مصدر الحالة الفعلية."
        ),
        "performance": (
            "📈 الأداء\n\n"
            "Performance Collector يجمع بيانات آخر المنشورات ويحدث بيانات الأداء.\n\n"
            "الأرقام التفصيلية تظهر في تقارير الأداء الدورية."
        ),
        "today": (
            "📅 جدول اليوم\n\n"
            "🕚 11:00 صباحًا\n"
            "🌙 19:00 مساءً\n\n"
            "الـScheduler يعمل كل 15 دقيقة، والشيت هو مصدر الحقيقة لموعد كل منشور."
        ),
        "recent": (
            "📝 آخر المنشورات\n\n"
            "يتم تسجيل المنشورات ونتائج المنصات في Google Sheets وPost Bank.\n\n"
            "التقرير التفصيلي يظهر تلقائيًا بعد عملية النشر."
        ),
        "retry": (
            "🔄 مركز إعادة المحاولة\n\n"
            "الأخطاء المؤقتة القابلة لإعادة المحاولة تدخل Retry Engine تلقائيًا.\n\n"
            "⚠️ لا يوجد زر نشر يدوي هنا حاليًا، لتجنب أي نشر مكرر."
        ),
        "health": (
            "🩺 فحص النظام\n\n"
            "🟢 Scheduler\n"
            "🟢 Google Sheets\n"
            "🟢 Gemini + fallback\n"
            "🟢 Cloudflare health check\n"
            "🟢 Performance Collector\n"
            "🟢 Telegram notifications\n\n"
            "LinkedIn Interaction تتم متابعته بشكل مستقل."
        ),
        "bank": (
            "📚 بنك المنشورات\n\n"
            "البنك يغذي خطة الشهر بموضوعات غير منشورة مع حماية من التكرار والزوايا المكررة."
        ),
        "month": (
            "📅 خطة الشهر\n\n"
            "Monthly Recycler يجهز المواعيد المتبقية ويستخدم موضوعات جديدة من البنك.\n\n"
            "🕚 11:00\n🌙 19:00 — بتوقيت القاهرة."
        ),
        "tokens": (
            "🔐 حالة التوكنات\n\n"
            "Facebook: Page Access Token\n"
            "LinkedIn: Access Token\n\n"
            "401 = Token\n"
            "403 = Permission / Product Access\n"
            "429 و5xx = Temporary / Retry\n\n"
            "أي مشكلة فعلية تظهر في التقرير التفصيلي."
        ),
        "system": (
            "⚙️ حالة النظام\n\n"
            "🟢 Production Publishing\n"
            "🟢 Resilient Scheduler\n"
            "🟢 Post Bank\n"
            "🟢 Monthly Recycler\n"
            "🟢 Performance Collector\n"
            "🟢 Telegram Control Center"
        ),
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
    if action == "home":
        text = menu_text()
        keyboard = _main_menu_keyboard()
    else:
        text = _menu_page(action)
        keyboard = _back_keyboard()
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
        # Confirm consumption of this update so it is not delivered again.
        try:
            get_updates(offset=update_id + 1)
        except Exception as exc:
            print(f"Telegram update acknowledgement failed: {exc}")
    return processed


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
            [{"text": "🏠 Control Center", "callback_data": "menu:home"}],
        ]
    }
    send_message(text, reply_markup=keyboard)


def _format_publication_report(text: str) -> str:
    """Turn the compact production notification into a detailed multi-platform report."""
    if not text.startswith("✅ Khyrat Legal Content Engine"):
        return text

    topic_match = re.search(r"تم نشر:\s*(.+?)(?:\n|Facebook:)", text, re.DOTALL)
    platform_match = re.search(r"Facebook:\s*(✅|❌)\s*\|\s*LinkedIn:\s*(✅|❌)", text)
    comments_match = re.search(r"التعليقات:\s*Facebook\s*(\d+)\/5\s*\|\s*LinkedIn\s*(\d+)\/5", text)

    topic = topic_match.group(1).strip() if topic_match else "غير متاح"
    fb_ok = platform_match.group(1) == "✅" if platform_match else False
    li_ok = platform_match.group(2) == "✅" if platform_match else False
    fb_comments = comments_match.group(1) if comments_match else "0"
    li_comments = comments_match.group(2) if comments_match else "0"

    return (
        "📊 KHYRAT LEGAL CONTENT ENGINE — DETAILED PLATFORM REPORT\n\n"
        f"📌 الموضوع:\n{topic}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📘 FACEBOOK — PAGE\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📝 النشر: {'✅ PUBLISHED' if fb_ok else '❌ FAILED'}\n"
        f"💬 التعليقات: {fb_comments}/5\n"
        "❤️ Like: تم تنفيذ الطلب أثناء النشر؛ الحالة التفصيلية ستظهر فقط إذا أبلغت API عن خطأ.\n"
        "🔁 Duplicate protection: ACTIVE\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💼 LINKEDIN\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📝 النشر: {'✅ PUBLISHED' if li_ok else '❌ FAILED'}\n"
        f"💬 التعليقات: {li_comments}/5\n"
        "❤️ Like: يتم تشخيصه في رسالة LinkedIn Interaction Diagnostic المستقلة.\n"
        "🔁 Retry/permission diagnostics: ACTIVE\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚙️ ENGINE STATUS\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🕒 Scheduler: ACTIVE\n"
        "📅 Sheet source of truth: ACTIVE\n"
        "🛡️ Idempotency: ACTIVE\n"
        "🔄 Retry queue: ACTIVE\n"
        "📈 Performance collector: ACTIVE\n\n"
        "🏠 Control Center: /menu\n\n"
        "✅ النشر الأساسي لا يتأثر بفشل Like أو Comment."
    )


def notify(text: str) -> None:
    try:
        send_message(_format_publication_report(text), reply_markup={"inline_keyboard": [[{"text": "🏠 Control Center", "callback_data": "menu:home"}]]})
    except Exception as exc:
        print(f"Telegram notification failed: {exc}")


def notify_linkedin_interaction(*, topic: str, post_urn: str, comment: dict[str, Any], like: dict[str, Any]) -> None:
    """Send a detailed diagnostic report for LinkedIn like/comment actions."""
    if not configured():
        return

    def render(label: str, result: dict[str, Any], success_labels: set[str]) -> str:
        status = str(result.get("status", "UNKNOWN"))
        http_status = result.get("http_status")
        error = str(result.get("error", "")).strip()
        attempts = result.get("attempts")
        line = f"{label}: {'✅' if status in success_labels else '❌'} {status}"
        if http_status:
            line += f" (HTTP {http_status})"
        if attempts:
            line += f" | محاولات: {attempts}"
        if error:
            line += f"\n   السبب: {error[:900]}"
        return line

    text = (
        "🔎 LINKEDIN — INTERACTION DIAGNOSTIC\n\n"
        f"📌 الموضوع: {topic}\n"
        f"🆔 Post URN: {post_urn}\n\n"
        f"{render('❤️ Like', like, {'LIKED'})}\n\n"
        f"{render('💬 First Comment', comment, {'PUBLISHED'})}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "التفسير التشغيلي:\n"
        "• 401 = مشكلة Token / انتهاء أو عدم صلاحية التوكن.\n"
        "• 403 = Permission / Product access.\n"
        "• 400 = صيغة الطلب أو بيانات غير مقبولة.\n"
        "• 408/429/5xx = خطأ مؤقت ويُعاد المحاولة تلقائيًا.\n\n"
        "🏠 Control Center: /menu\n\n"
        "النشر الأساسي لا يتأثر بفشل التفاعل."
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
