from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote


def _bot():
    from src import telegram_bot
    return telegram_bot


def send_review_request(*, row_number: int, topic: str, post: str, reason: str, sheet_id: str, status: str) -> None:
    bot = _bot()
    if not bot.configured():
        print("Telegram not configured; review notification skipped.")
        return
    sheet_url = f"https://docs.google.com/spreadsheets/d/{quote(sheet_id, safe='')}/edit"
    text = (
        "🚨 Khyrat Legal Content Engine\n\n"
        f"الحالة: {status}\nالصف: {row_number}\nالموضوع: {topic}\n\n"
        f"سبب المراجعة:\n{reason or 'يحتاج مراجعة قانونية.'}\n\n"
        f"محتوى المنشور:\n{post[:3500]}\n\n"
        "الخطوات:\n1) افتح المحتوى من الزر.\n2) راجع النص والمصادر.\n"
        "3) اختر موافقة أو رفض.\n4) الموافقة تسمح بنشر هذا البوست فقط؛ باقي الأتمتة تستمر طبيعيًا."
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
    bot.send_message(text, reply_markup=keyboard)


def _format_publication_report(text: str) -> str:
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
        "━━━━━━━━━━━━━━━━━━\n📘 FACEBOOK — PAGE\n━━━━━━━━━━━━━━━━━━\n"
        f"📝 النشر: {'✅ PUBLISHED' if fb_ok else '❌ FAILED'}\n"
        f"💬 التعليقات: {fb_comments}/5\n"
        "❤️ Like: تم تنفيذ الطلب أثناء النشر؛ الحالة التفصيلية ستظهر فقط إذا أبلغت API عن خطأ.\n"
        "🔁 Duplicate protection: ACTIVE\n\n━━━━━━━━━━━━━━━━━━\n💼 LINKEDIN\n━━━━━━━━━━━━━━━━━━\n"
        f"📝 النشر: {'✅ PUBLISHED' if li_ok else '❌ FAILED'}\n"
        f"💬 التعليقات: {li_comments}/5\n"
        "❤️ Like: يتم تشخيصه في رسالة LinkedIn Interaction Diagnostic المستقلة.\n"
        "🔁 Retry/permission diagnostics: ACTIVE\n\n━━━━━━━━━━━━━━━━━━\n⚙️ ENGINE STATUS\n━━━━━━━━━━━━━━━━━━\n"
        "🕒 Scheduler: ACTIVE\n📅 Sheet source of truth: ACTIVE\n🛡️ Idempotency: ACTIVE\n"
        "🔄 Retry queue: ACTIVE\n📈 Performance collector: ACTIVE\n\n🏠 Control Center: /menu\n\n"
        "✅ النشر الأساسي لا يتأثر بفشل Like أو Comment."
    )


def notify(text: str) -> None:
    bot = _bot()
    try:
        bot.send_message(
            _format_publication_report(text),
            reply_markup={"inline_keyboard": [[{"text": "🏠 Control Center", "callback_data": "menu:home"}] ]},
        )
    except Exception as exc:
        print(f"Telegram notification failed: {exc}")


def notify_linkedin_interaction(*, topic: str, post_urn: str, comment: dict[str, Any], like: dict[str, Any]) -> None:
    bot = _bot()
    if not bot.configured():
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
        f"📌 الموضوع: {topic}\n🆔 Post URN: {post_urn}\n\n"
        f"{render('❤️ Like', like, {'LIKED'})}\n\n"
        f"{render('💬 First Comment', comment, {'PUBLISHED'})}\n\n"
        "━━━━━━━━━━━━━━━━━━\nالتفسير التشغيلي:\n"
        "• 401 = مشكلة Token / انتهاء أو عدم صلاحية التوكن.\n"
        "• 403 = Permission / Product access.\n"
        "• 400 = صيغة الطلب أو بيانات غير مقبولة.\n"
        "• 408/429/5xx = خطأ مؤقت ويُعاد المحاولة تلقائيًا.\n\n"
        "🏠 Control Center: /menu\n\nالنشر الأساسي لا يتأثر بفشل التفاعل."
    )
    notify(text)
