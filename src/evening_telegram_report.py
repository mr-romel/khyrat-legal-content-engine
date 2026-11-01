from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from sheets import HEADERS, create_service, get_values, row_to_dict
from telegram_bot import send_message

TZ = ZoneInfo("Africa/Cairo")

PLATFORMS = [
    ("Facebook", "Facebook Status", "Facebook Post URL", "Facebook Post ID"),
    ("LinkedIn", "LinkedIn Status", "LinkedIn Post URL", "LinkedIn Post ID"),
    ("Blogger", "Blogger Status", "Blogger URL", "Blogger Post ID"),
]


def _today(value: str, today) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            if datetime.strptime(raw[:10], fmt).date() == today:
                return True
        except ValueError:
            pass
    return raw[:10] == today.isoformat()


def _cell(row: dict[str, str], key: str) -> str:
    return str(row.get(key, "") or "").strip()


def _platform_result(row: dict[str, str], label: str, status_key: str, url_key: str, id_key: str) -> tuple[str, str]:
    status = _cell(row, status_key).upper()
    url = _cell(row, url_key)
    post_id = _cell(row, id_key)
    error = _cell(row, f"{label} Last Error") or _cell(row, "آخر خطأ")

    if url.startswith(("https://", "http://")):
        return f"نُشر — {url}", ""
    if status in {"PUBLISHED", "SUCCESS", "DONE"} or post_id:
        detail = "يوجد status/ID لكن لا يوجد رابط منشور محفوظ؛ يلزم التحقق من الرابط."
        if error:
            detail += f" آخر خطأ مسجل: {error}"
        return f"غير مؤكد — {detail}", ""
    if status in {"FAILED", "ERROR", "PARTIAL_FAILED"} or error:
        return f"لم يُنشر — {error or status or 'فشل غير محدد السبب'}", ""
    if status in {"PROCESSING", "PENDING", "READY", "QUEUED", "SCHEDULED"}:
        return f"لم يكتمل — الحالة الحالية: {status}", ""
    return f"لا يوجد إثبات نشر — الحالة: {status or 'فارغة'}", ""


def _video_results(row: dict[str, str]) -> list[str]:
    results = []
    reel_status = _cell(row, "Reel Status").upper()
    reel_fb_id = _cell(row, "Reel Facebook ID")
    reel_error = _cell(row, "Reel Last Error")
    if reel_fb_id:
        results.append(f"Facebook Reel: نُشر بمعرّف {reel_fb_id}؛ لا يوجد حقل رابط Reel مستقل محفوظ للتحقق من الرابط.")
    elif reel_status in {"PUBLISHED", "SUCCESS", "DONE"}:
        results.append("Facebook Reel: حالة منشور لكن لا يوجد Reel Facebook ID محفوظ؛ النشر غير مؤكد.")
    elif reel_status in {"FAILED", "ERROR", "PARTIAL_FAILED"} or reel_error:
        results.append(f"Facebook Reel: لم يُنشر/تعطل — {reel_error or reel_status}")
    elif reel_status in {"REVIEW", "AWAITING_APPROVAL", "PENDING_APPROVAL"}:
        results.append("Facebook Reel: ينتظر موافقتك؛ عدم النشر هنا مقصود وليس فشلًا.")
    elif reel_status:
        results.append(f"Facebook Reel: لم يكتمل — الحالة: {reel_status}")
    else:
        results.append("Facebook Reel: لا يوجد سجل حالة لهذا الصف.")

    yt_url = _cell(row, "Reel YouTube URL")
    yt_id = _cell(row, "Reel YouTube ID")
    if yt_url.startswith(("https://", "http://")):
        results.append(f"YouTube Shorts: نُشر — {yt_url}")
    elif yt_id:
        results.append(f"YouTube Shorts: يوجد Video ID ({yt_id}) لكن لا يوجد رابط محفوظ؛ يلزم التحقق.")
    elif reel_status in {"REVIEW", "AWAITING_APPROVAL", "PENDING_APPROVAL"}:
        results.append("YouTube Shorts: ينتظر اعتماد الريل ونشره أولًا.")
    else:
        results.append("YouTube Shorts: لا يوجد رابط أو Video ID محفوظ يثبت النشر.")
    return results


def main() -> int:
    now = datetime.now(TZ)
    if os.getenv("FORCE_EVENING_REPORT", "").strip().lower() not in {"1", "true", "yes"} and now.hour != 22:
        print(f"Skipping: local Cairo time is {now:%H:%M}; report is only sent at 22:00.")
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        raise RuntimeError("Telegram bot token/chat ID are required.")

    raw_credentials = (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_CREDENTIALS") or "").strip()
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    if not raw_credentials or not sheet_id:
        raise RuntimeError("Google Sheets credentials and ID are required for a factual report.")

    service = create_service(json.loads(raw_credentials))
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Content").strip() or "Content"
    values = get_values(service, sheet_id, f"{sheet_name}!A:BG")
    headers = [str(x or "").strip() for x in values[0]] if values else HEADERS
    rows = [row_to_dict(row, headers) for row in values[1:]]
    today_rows = [r for r in rows if _today(r.get("تاريخ النشر", ""), now.date())]
    today_rows.sort(key=lambda r: str(r.get("ساعة النشر", "")))

    lines = [
        "تقرير نتيجة النشر المسائي",
        f"التاريخ: {now:%Y-%m-%d} | الساعة: {now:%H:%M} بتوقيت القاهرة",
        "",
    ]
    if not today_rows:
        lines.extend([
            "لا توجد صفوف خطة بتاريخ اليوم في Google Sheets.",
            "النتيجة: لا يمكن إثبات تنفيذ منشورات الخطة لهذا اليوم من سجل الجدول.",
        ])
    else:
        published = failed = unverified = 0
        for row in today_rows:
            topic = _cell(row, "الموضوع") or "موضوع غير محدد"
            slot = _cell(row, "ساعة النشر") or "موعد غير محدد"
            lines.extend(["", f"الموضوع: {topic} | الموعد: {slot}"])
            for label, status_key, url_key, id_key in PLATFORMS:
                result, _ = _platform_result(row, label, status_key, url_key, id_key)
                lines.append(f"• {label}: {result}")
                if "نُشر — http" in result:
                    published += 1
                elif "لم يُنشر" in result or "لم يكتمل" in result:
                    failed += 1
                else:
                    unverified += 1
            for video_line in _video_results(row):
                lines.append(f"• {video_line}")
                if "نُشر — http" in video_line:
                    published += 1
                elif "لم يُنشر" in video_line or "لا يوجد رابط" in video_line:
                    failed += 1
                else:
                    unverified += 1
            if _cell(row, "Blogger Last Error"):
                lines.append(f"• سبب تعطل Blogger المسجل: {_cell(row, 'Blogger Last Error')}")
            if _cell(row, "آخر خطأ"):
                lines.append(f"• آخر خطأ عام: {_cell(row, 'آخر خطأ')}")

        lines.extend([
            "",
            f"ملخص التحقق: روابط نشر مؤكدة: {published} | حالات فشل/عدم اكتمال: {failed} | حالات تحتاج تحققًا أو موافقة: {unverified}",
            "ملاحظة: التقرير يعتمد على الروابط والمعرّفات وحالات التنفيذ المسجلة في Google Sheets؛ لا يدّعي التحقق من صفحة المنصة نفسها إذا لم يُحفظ رابطها.",
        ])

    result = send_message("\n".join(lines))
    if not result:
        raise RuntimeError("Telegram did not return a sent message result.")
    print(f"Evening Telegram publishing report sent. message_id={result.get('message_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
