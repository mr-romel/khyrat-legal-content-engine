from __future__ import annotations

from datetime import date

from src.sheets import update_row
from src.recycler_rules import RECYCLE_MARKER, POSTING_TIMES, normalize_topic, is_published, historically_used_topics


def migrate_future_slots(service, spreadsheet_id: str, sheet_name: str, values: list[list[str]], current: date, month_key: str) -> int:
    marker = f"{RECYCLE_MARKER}:{month_key}"
    desired: set[tuple[str, str]] = set()
    candidates: list[tuple[int, dict[str, str]]] = []
    for row_number, raw in enumerate(values[1:], start=2):
        row = _row(raw)
        if marker not in row.get("ملاحظات", ""): continue
        publish_date, old_time = row.get("تاريخ النشر", "").strip(), row.get("ساعة النشر", "").strip()
        if not publish_date or not old_time or publish_date < current.isoformat() or is_published(row): continue
        if row.get("الحالة", "").strip().upper() == "CANCELLED": continue
        if old_time in POSTING_TIMES: desired.add((publish_date, old_time))
        else: candidates.append((row_number, row))
    changed = 0
    for row_number, row in candidates:
        publish_date, old_time = row["تاريخ النشر"].strip(), row["ساعة النشر"].strip()
        target_time = "11:00" if old_time in {"14:00", "08:00", "10:00"} else "19:00"
        target = (publish_date, target_time)
        notes = row.get("ملاحظات", "")
        if target in desired:
            update_row(service, spreadsheet_id, sheet_name, row_number, {"الحالة": "CANCELLED", "ملاحظات": f"{notes} | تم إلغاء slot قديم {old_time} لتفادي التكرار بعد اعتماد 11:00 و19:00."})
        else:
            update_row(service, spreadsheet_id, sheet_name, row_number, {"ساعة النشر": target_time, "ملاحظات": f"{notes} | تم ترحيل الموعد تلقائيًا من {old_time} إلى {target_time} بتوقيت القاهرة."})
            desired.add(target)
        changed += 1
    return changed


def replace_remaining_current_month_slots(service, spreadsheet_id: str, sheet_name: str, values: list[list[str]], current: date, current_key: str, topic_pool: list[dict[str, str]]) -> int:
    used = historically_used_topics(values, current_key)
    marker = f"{RECYCLE_MARKER}:{current_key}"
    replacements = []
    for row_number, raw in enumerate(values[1:], start=2):
        row = _row(raw)
        publish_date, posting_time, notes = row.get("تاريخ النشر", "").strip(), row.get("ساعة النشر", "").strip(), row.get("ملاحظات", "")
        if not publish_date or publish_date < current.isoformat() or posting_time not in POSTING_TIMES: continue
        if marker in notes or is_published(row) or row.get("الحالة", "").strip().upper() in {"CANCELLED", "PARTIAL_FAILED"}: continue
        replacements.append((row_number, row))
    available = [x for x in topic_pool if normalize_topic(x["topic"]) not in used]
    changed = 0
    for index, (row_number, row) in enumerate(replacements):
        if index >= len(available): break
        brief = available[index]
        used.add(normalize_topic(brief["topic"]))
        posting_time = row["ساعة النشر"].strip()
        update_row(service, spreadsheet_id, sheet_name, row_number, {
            "الموضوع": f"{brief['topic'].strip()} — زاوية جديدة: {brief['angle'].strip()}",
            "المصادر القانونية": brief["legal_sources"].strip(), "الحالة": "READY", "آخر خطأ": "",
            "ملاحظات": f"{RECYCLE_MARKER}:{current_key} | الموضوع الأصلي: {brief['topic'].strip()} | القسم: {brief['category']} | زاوية: {brief['angle'].strip()} | الصيغة: {brief['format'].strip()} | الهدف: {brief['objective'].strip()} | Slot: {posting_time} | المصدر: 500-Topic-Bank replacement | لا يعاد استخدام موضوع منشور سابقًا أو نفس الموضوع بزاوية أخرى | ساعة النشر مثبتة تلقائيًا",
        })
        changed += 1
    return changed


def _row(raw: list[str]) -> dict[str, str]:
    from src.sheets import row_to_dict
    return row_to_dict(raw)
