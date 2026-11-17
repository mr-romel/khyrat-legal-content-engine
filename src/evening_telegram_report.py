from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sheets import HEADERS, create_service, get_values, row_to_dict
from telegram_bot import send_message
from ga4_reporting import DEFAULT_PROPERTY_ID, _analytics_service, build_snapshot, read_lead_summary

TZ = ZoneInfo("Africa/Cairo")  # The worker gates scheduled runs to exactly 22:00 Cairo local time.
# The acquisition block uses GA4 events for intent signals and the Lead CRM tab for confirmed inquiries.

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


def _fmt_metric(value) -> str:
    if value is None:
        return "غير متاح"
    try:
        number = float(value)
        return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"
    except (TypeError, ValueError):
        return "غير متاح"


def _acquisition_lines(snapshot: dict) -> list[str]:
    current = snapshot.get("current", {}).get("metrics", {})
    events = snapshot.get("events", []) or []
    event_map = {str(row.get("eventName", "")): row.get("eventCount") for row in events}
    event_data_available = bool(events)

    def event_value(name: str) -> str:
        value = event_map.get(name)
        if value is None and not event_data_available:
            return "لا توجد بيانات أحداث بعد"
        return _fmt_metric(value if value is not None else 0)

    leads = snapshot.get("lead_crm", {}) or {}
    return [
        "",
        "📊 اكتساب العملاء — آخر 7 أيام مكتملة",
        f"الفترة: {snapshot.get('period', {}).get('start', '')} إلى {snapshot.get('period', {}).get('end', '')}",
        f"• جلسات الموقع: {_fmt_metric(current.get('sessions'))}",
        f"• المستخدمون النشطون: {_fmt_metric(current.get('activeUsers'))}",
        f"• ضغطات طلب الاستشارة (consultation_click): {event_value('consultation_click')}",
        f"• ضغطات التواصل (contact_click): {event_value('contact_click')}",
        f"• الاستفسارات المسجلة في CRM: {_fmt_metric(leads.get('inquiries_received'))}",
        f"• العملاء المحتملون المؤهلون: {_fmt_metric(leads.get('qualified_leads'))}",
        f"• العملاء المؤكدون: {_fmt_metric(leads.get('clients_confirmed'))}",
        "قاعدة القياس: الزيارة أو ضغطة التواصل ليست عميلًا. العميل يُحسب فقط من سجل CRM بعد تأكيد حالته.",
    ]


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
        "تقرير نتيجة النشر المسائي واكتساب العملاء",
        f"التاريخ: {now:%Y-%m-%d} | الساعة: {now:%H:%M} بتوقيت القاهرة",
        "",
    ]
    property_id = os.getenv("GA4_PROPERTY_ID", DEFAULT_PROPERTY_ID).strip()
    try:
        lead_summary = read_lead_summary()
    except Exception as crm_exc:
        lead_summary = {"status": "UNAVAILABLE", "inquiries_received": None, "qualified_leads": None, "clients_confirmed": None}
        crm_error = str(crm_exc)[:300]
    else:
        crm_error = ""
    try:
        snapshot = build_snapshot(_analytics_service(), property_id, now.date() - timedelta(days=1))
        ga4_error = ""
    except Exception as analytics_exc:
        ga4_error = str(analytics_exc)[:500]
        end_date = now.date() - timedelta(days=1)
        current_start = end_date - timedelta(days=6)
        snapshot = {
            "period": {"start": current_start.isoformat(), "end": end_date.isoformat()},
            "current": {"metrics": {"sessions": None, "activeUsers": None}},
            "events": [],
        }
    snapshot["lead_crm"] = lead_summary
    lines.extend(_acquisition_lines(snapshot))
    if ga4_error:
        lines.append(f"• حالة GA4: غير متاحة — {ga4_error[:250]}")
    if crm_error:
        lines.append(f"• حالة سجل العملاء CRM: غير متاح — {crm_error[:250]}")
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
