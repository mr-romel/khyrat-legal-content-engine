from __future__ import annotations

import json
import os

from sheets import create_service, get_values, row_to_dict, update_row
from telegram_bot import answer_callback, authorized_user, edit_message, get_updates, notify


def main() -> None:
    service_account = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Content").strip() or "Content"

    if not service_account or not sheet_id:
        raise RuntimeError("Google Sheets configuration is missing.")

    service = create_service(json.loads(service_account))
    updates = get_updates()
    if not updates:
        print("Telegram control: no pending updates.")
        return

    values = get_values(service, sheet_id, f"{sheet_name}!A:U")
    rows = {index: row_to_dict(raw) for index, raw in enumerate(values[1:], start=2)}

    max_update_id = 0

    for update in updates:
        max_update_id = max(max_update_id, int(update.get("update_id", 0)))
        callback = update.get("callback_query")
        if callback:
            user = callback.get("from", {})
            if not authorized_user(user.get("id", "")):
                answer_callback(callback.get("id", ""), "⛔ غير مصرح لك.")
                continue

            data = str(callback.get("data", ""))
            action, _, raw_row = data.partition(":")
            try:
                row_number = int(raw_row)
            except ValueError:
                answer_callback(callback.get("id", ""), "بيانات غير صالحة.")
                continue

            row = rows.get(row_number)
            if not row:
                answer_callback(callback.get("id", ""), "الصف غير موجود.")
                continue

            current_status = str(row.get("الحالة", "")).strip().upper()

            if action == "approve":
                if current_status not in {"NEEDS_REVIEW", "PENDING_REVIEW"}:
                    answer_callback(callback.get("id", ""), f"الحالة الحالية: {current_status}")
                    continue
                update_row(
                    service,
                    sheet_id,
                    sheet_name,
                    row_number,
                    {
                        "الحالة": "APPROVED",
                        "آخر خطأ": "",
                    },
                )
                answer_callback(callback.get("id", ""), "تمت الموافقة. سينشر في أقرب تشغيل للنشر.")
                message = callback.get("message", {})
                if message.get("chat", {}).get("id") and message.get("message_id"):
                    edit_message(
                        str(message["chat"]["id"]),
                        int(message["message_id"]),
                        f"✅ تمت الموافقة على الصف {row_number}.\n\nالموضوع: {row.get('الموضوع','')}\n\nسيتم نشره في أقرب تشغيل آمن للنشر.",
                    )

            elif action == "reject":
                if current_status not in {"NEEDS_REVIEW", "PENDING_REVIEW"}:
                    answer_callback(callback.get("id", ""), f"الحالة الحالية: {current_status}")
                    continue
                update_row(
                    service,
                    sheet_id,
                    sheet_name,
                    row_number,
                    {
                        "الحالة": "REJECTED",
                        "آخر خطأ": "Rejected from Telegram review.",
                    },
                )
                answer_callback(callback.get("id", ""), "تم رفض المنشور.")
                message = callback.get("message", {})
                if message.get("chat", {}).get("id") and message.get("message_id"):
                    edit_message(
                        str(message["chat"]["id"]),
                        int(message["message_id"]),
                        f"❌ تم رفض الصف {row_number}.\n\nالموضوع: {row.get('الموضوع','')}",
                    )

        message = update.get("message")
        if message and authorized_user(message.get("from", {}).get("id", "")):
            text = str(message.get("text", "")).strip().lower()
            if text in {"/help", "/start"}:
                notify(
                    "🤖 Khyrat Legal Content Engine\n\n"
                    "/help — شرح الأوامر\n"
                    "/status — حالة النظام المختصرة\n\n"
                    "المراجعات القانونية ستصل هنا تلقائيًا مع أزرار الموافقة والرفض."
                )
            elif text == "/status":
                notify("🟢 Telegram Control يعمل. المراجعات والتنبيهات جاهزة.")

    if max_update_id:
        # Confirm all processed updates so they are not returned again.
        get_updates(offset=max_update_id + 1)


if __name__ == "__main__":
    main()
