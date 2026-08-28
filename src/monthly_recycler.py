from __future__ import annotations

from datetime import date

from src.post_bank import get_bank_rows
from src.sheets import get_values, row_to_dict, insert_row_at_top
from src.topic_bank_500 import TOPIC_BANK
from src.utils import parse_date
from src.recycler_rules import (
    RECYCLE_MARKER, POSTING_TIMES, ANGLE_LIBRARY, CATEGORY_ORDER,
    month_key, normalize_topic, is_published, historically_used_topics,
    source_rows, prepared_slots, posting_days, topic_pool_for_month,
    brief_notes, legacy_source_for_slot,
)
from src.recycler_slots import migrate_future_slots, replace_remaining_current_month_slots


def recycle_month_if_needed(*, service, spreadsheet_id: str, sheet_name: str, current: date) -> int:
    values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")
    bank_rows = get_bank_rows(service, spreadsheet_id)
    current_key = current.strftime("%Y-%m")
    migrated = migrate_future_slots(service, spreadsheet_id, sheet_name, values, current, current_key)
    if migrated:
        values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")

    historical_used = historically_used_topics(values, current_key)
    source = source_rows(values, bank_rows)
    pool = topic_pool_for_month(current_key, historical_used)
    replaced = replace_remaining_current_month_slots(
        service, spreadsheet_id, sheet_name, values, current, current_key, pool
    )
    if replaced:
        values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")
        historical_used = historically_used_topics(values, current_key)
        pool = topic_pool_for_month(current_key, historical_used)

    days = posting_days(current.year, current.month, current.day)
    expected = {
        (f"{current.year:04d}-{current.month:02d}-{day:02d}", posting_time)
        for day in days for posting_time in POSTING_TIMES
    }
    prepared = prepared_slots(values, current_key)
    missing = sorted(expected - prepared)
    if not missing:
        print(f"Monthly recycler: {current_key} is fully prepared for 11:00 and 19:00 Cairo time.")
        return migrated + replaced

    print(f"Monthly recycler: creating {len(missing)} missing slots for {current_key}.")
    print(f"Monthly recycler: 500-topic bank active; {len(pool)} never-published topics available.")
    created = 0
    used_topics = historically_used_topics(values, current_key)
    bank_index = 0
    for index, (publish_date, posting_time) in enumerate(missing):
        brief = None
        while bank_index < len(pool):
            candidate = pool[bank_index]
            bank_index += 1
            if normalize_topic(candidate["topic"]) not in used_topics:
                brief = candidate
                break
        if brief is None:
            legacy = legacy_source_for_slot(source, index, used_topics)
            if legacy is None:
                print("Monthly recycler: no unused topic remains for a missing slot; stopping safely.")
                break
            original = legacy["الموضوع"].strip()
            angle = ANGLE_LIBRARY[index % len(ANGLE_LIBRARY)]
            row = {
                "ID": f"{publish_date.replace('-', '')}-{posting_time.replace(':', '')}-R{index + 1:03d}",
                "الموضوع": f"{original} — زاوية جديدة: {angle}",
                "تاريخ النشر": publish_date, "ساعة النشر": posting_time,
                "نوع الجدولة": "DATE_TIME", "الحالة": "READY",
                "المصادر القانونية": legacy.get("المصادر القانونية", ""),
                "ملاحظات": f"{RECYCLE_MARKER}:{current_key} | الموضوع الأصلي: {original} | زاوية: {angle} | Slot: {posting_time} | المصدر: Content/PostBank fallback | ساعة النشر مثبتة تلقائيًا",
            }
            used_topics.add(normalize_topic(original))
        else:
            original = brief["topic"].strip()
            row = {
                "ID": f"{publish_date.replace('-', '')}-{posting_time.replace(':', '')}-R{index + 1:03d}",
                "الموضوع": f"{original} — زاوية جديدة: {brief['angle'].strip()}",
                "تاريخ النشر": publish_date, "ساعة النشر": posting_time,
                "نوع الجدولة": "DATE_TIME", "الحالة": "READY",
                "المصادر القانونية": brief["legal_sources"].strip(),
                "ملاحظات": brief_notes(current_key, brief, posting_time),
            }
            used_topics.add(normalize_topic(original))
        insert_row_at_top(service, spreadsheet_id, sheet_name, row)
        created += 1

    print(f"Monthly recycler: created {created} missing rows for {current_key}; target = 11:00 and 19:00 Cairo time.")
    return migrated + replaced + created
