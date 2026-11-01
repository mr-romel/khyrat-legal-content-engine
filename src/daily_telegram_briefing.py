from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from sheets import HEADERS, create_service, get_values, row_to_dict
from telegram_bot import send_message
from blogger_trend_worker import collect_candidates

TZ = ZoneInfo("Africa/Cairo")  # All displayed dates and times use Egypt local time.


def _today(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date() == datetime.now(TZ).date()
        except ValueError:
            pass
    return raw[:10] == datetime.now(TZ).date().isoformat()


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        raise RuntimeError("Telegram bot token/chat ID are required; refusing silent success.")

    raw_credentials = (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_CREDENTIALS") or "").strip()
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    if not raw_credentials or not sheet_id:
        raise RuntimeError("Google Sheets credentials and ID are required for a factual daily plan.")

    service = create_service(json.loads(raw_credentials))
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Content").strip() or "Content"
    values = get_values(service, sheet_id, f"{sheet_name}!A:BG")
    headers = [str(x or "").strip() for x in values[0]] if values else HEADERS
    rows = [row_to_dict(row, headers) for row in values[1:]]
    today_rows = [r for r in rows if _today(r.get("تاريخ النشر", ""))]
    today_rows.sort(key=lambda r: str(r.get("ساعة النشر", "")))

    lines = [
        "صباح الخير — تقرير تشغيل النشر اليومي",
        f"التاريخ: {datetime.now(TZ).strftime('%Y-%m-%d')} (القاهرة)",
        "",
        "جدول المنصات:",
    ]
    if today_rows:
        for row in today_rows:
            topic = row.get("الموضوع", "موضوع غير محدد").strip() or "موضوع غير محدد"
            time = row.get("ساعة النشر", "").strip() or "غير محدد في الجدول"
            status = row.get("الحالة", "").strip() or "غير محدد"
            fb = row.get("Facebook Status", "").strip()
            li = row.get("LinkedIn Status", "").strip()
            blogger = row.get("Blogger Status", "").strip()
            reel = row.get("Reel Status", "").strip()
            lines.append(f"• {time} — Facebook / LinkedIn: {topic} | حالة الصف: {status}")
            if blogger:
                lines.append(f"  Blogger: {blogger}")
            if reel:
                lines.append(f"  Reel: {reel}")
            if fb or li:
                lines.append(f"  حالة Facebook: {fb or 'بانتظار التنفيذ'} | LinkedIn: {li or 'بانتظار التنفيذ'}")
    else:
        lines.append("• لا يوجد صف نشر اجتماعي مؤكد بتاريخ اليوم في Google Sheets.")
        lines.append("  لن يتم اختراع موعد أو اعتبار صف قديم منشورًا على أنه خطة اليوم.")

    lines.extend([
        "",
        "مقالات الترند:",
    ])
    try:
        candidates = collect_candidates()
        if candidates:
            lines.append("• المستهدف: مقال ترند قانوني واحد اليوم، بشرط اجتياز الصلة القانونية وعدم التكرار.")
            lines.append(f"• الموضوع المرشح حاليًا: {candidates[0]['title']}")
            lines.append("• موعد تشغيل ناشر الترند: 09:00 صباحًا بتوقيت القاهرة.")
        else:
            lines.append("• المستهدف: مقال واحد كحد أقصى؛ لا نشر إذا لم يظهر ترند قانوني مصري موثوق.")
    except Exception as exc:
        lines.append("• تعذر فحص مصادر الترند الآن؛ لن نعلن موضوعًا غير متحقق منه.")
        print(f"Trend candidate collection failed: {exc}")

    lines.extend([
        "",
        "الفيديو:",
        "• الريل يُرسل للمراجعة على تليجرام؛ النشر لا يتم قبل الموافقة.",
        "• YouTube Shorts يتبع الريل بعد الموافقة والتحقق من نجاح النشر.",
        "",
        "تنبيه تشغيلي: هذه خطة اليوم المستخرجة من الشيت، وليست إثبات نشر. أي فشل أو تأخير يجب أن يظهر في تقرير نتيجة مستقل مع السبب والرابط.",
    ])
    result = send_message("\n".join(lines))
    if not result:
        raise RuntimeError("Telegram did not return a sent message result.")
    print(f"Daily Telegram briefing sent. message_id={result.get('message_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
