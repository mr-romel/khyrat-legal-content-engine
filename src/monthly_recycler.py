from __future__ import annotations

import hashlib
from datetime import date

from post_bank import get_bank_rows
from sheets import get_values, insert_row_at_top, row_to_dict, update_row
from topic_bank_500 import TOPIC_BANK
from recycler_rules import (
    ANGLE_LIBRARY,
    POSTING_TIMES,
    RECYCLE_MARKER,
    brief_notes,
    historically_used_topics,
    is_published,
    legacy_source_for_slot,
    normalize_topic,
    prepared_slots,
    posting_days,
    source_rows,
)


def _migrate_future_slots(service, spreadsheet_id: str, sheet_name: str, values: list[list[str]], current: date, month_key: str) -> int:
    marker = f"{RECYCLE_MARKER}:{month_key}"
    desired: set[tuple[str, str]] = set()
    candidates: list[tuple[int, dict[str, str]]] = []
    for row_number, raw in enumerate(values[1:], start=2):
        row = row_to_dict(raw)
        if marker not in row.get("ملاحظات", ""): continue
        publish_date, publish_time = row.get("تاريخ النشر", "").strip(), row.get("ساعة النشر", "").strip()
        if not publish_date or not publish_time or publish_date < current.isoformat() or is_published(row): continue
        if row.get("الحالة", "").strip().upper() == "CANCELLED": continue
        if publish_time in POSTING_TIMES: desired.add((publish_date, publish_time))
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
    if changed: print(f"Monthly recycler: migrated {changed} future legacy slots to 11:00/19:00.")
    return changed


def _topic_pool_for_month(month_key: str, used_topics: set[str]) -> list[dict[str, str]]:
    seed = int(hashlib.sha256(month_key.encode("utf-8")).hexdigest()[:8], 16)
    categories = ("القانون الجنائي", "قانون الشركات والاستثمار", "قانون الأسرة", "قانون العمل الجديد", "القانون الإداري")
    pools: dict[str, list[dict[str, str]]] = {category: [] for category in categories}
    for item in TOPIC_BANK:
        if normalize_topic(item["topic"]) not in used_topics: pools[item["category"]].append(item)
    for offset, category in enumerate(categories):
        items = pools[category]
        if items:
            rotation = (seed + offset * 17) % len(items)
            pools[category] = items[rotation:] + items[:rotation]
    category_start = seed % len(categories)
    sequence: list[dict[str, str]] = []
    indexes = {category: 0 for category in categories}
    while len(sequence) < len(TOPIC_BANK):
        added = False
        for step in range(len(categories)):
            category = categories[(category_start + step) % len(categories)]
            index = indexes[category]
            if index >= len(pools[category]): continue
            sequence.append(pools[category][index]); indexes[category] += 1; added = True
        if not added: break
    return sequence


def _replace_remaining_current_month_slots(service, spreadsheet_id: str, sheet_name: str, values: list[list[str]], current: date, current_key: str, topic_pool: list[dict[str, str]]) -> int:
    historical_used = historically_used_topics(values, current_key)
    marker = f"{RECYCLE_MARKER}:{current_key}"
    replacements: list[tuple[int, dict[str, str]]] = []
    for row_number, raw in enumerate(values[1:], start=2):
        row = row_to_dict(raw)
        publish_date, posting_time = row.get("تاريخ النشر", "").strip(), row.get("ساعة النشر", "").strip()
        if not publish_date or publish_date < current.isoformat() or posting_time not in POSTING_TIMES or marker in row.get("ملاحظات", ""): continue
        if is_published(row) or row.get("الحالة", "").strip().upper() in {"CANCELLED", "PARTIAL_FAILED"}: continue
        replacements.append((row_number, row))
    available = [item for item in topic_pool if normalize_topic(item["topic"]) not in historical_used]
    changed = 0
    for index, (row_number, row) in enumerate(replacements):
        if index >= len(available): break
        brief = available[index]; historical_used.add(normalize_topic(brief["topic"]))
        posting_time = row.get("ساعة النشر", "").strip()
        update_row(service, spreadsheet_id, sheet_name, row_number, {"الموضوع": f"{brief['topic'].strip()} — زاوية جديدة: {brief['angle'].strip()}", "المصادر القانونية": brief["legal_sources"].strip(), "الحالة": "READY", "آخر خطأ": "", "ملاحظات": brief_notes(current_key, brief, posting_time, "500-Topic-Bank replacement")})
        changed += 1
    print(f"Monthly recycler: replaced {changed} remaining current-month unpublished slots with never-published bank topics.")
    return changed


def recycle_month_if_needed(*, service, spreadsheet_id: str, sheet_name: str, current: date) -> int:
    values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")
    bank_rows = get_bank_rows(service, spreadsheet_id)
    current_key = current.strftime("%Y-%m")
    migrated = _migrate_future_slots(service, spreadsheet_id, sheet_name, values, current, current_key)
    if migrated: values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")
    historical_used = historically_used_topics(values, current_key)
    source_rows_list = source_rows(values, bank_rows)
    topic_pool = _topic_pool_for_month(current_key, historical_used)
    replaced = _replace_remaining_current_month_slots(service, spreadsheet_id, sheet_name, values, current, current_key, topic_pool)
    if replaced:
        values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")
        historical_used = historically_used_topics(values, current_key)
        topic_pool = _topic_pool_for_month(current_key, historical_used)
    days = posting_days(current.year, current.month, current.day)
    expected_slots = {(f"{current.year:04d}-{current.month:02d}-{day:02d}", posting_time) for day in days for posting_time in POSTING_TIMES}
    prepared = prepared_slots(values, current_key)
    missing_slots = sorted(expected_slots - prepared)
    if not missing_slots:
        print(f"Monthly recycler: {current_key} is fully prepared for 11:00 and 19:00 Cairo time.")
        return migrated + replaced
    print(f"Monthly recycler: creating {len(missing_slots)} missing slots for {current_key}.")
    used_topics = historically_used_topics(values, current_key)
    bank_index = 0; created = 0
    for index, (publish_date, posting_time) in enumerate(missing_slots):
        brief = None
        while bank_index < len(topic_pool):
            candidate = topic_pool[bank_index]; bank_index += 1
            if normalize_topic(candidate["topic"]) not in used_topics: brief = candidate; break
        if brief is None:
            legacy = legacy_source_for_slot(source_rows_list, index, used_topics)
            if legacy is None:
                print("Monthly recycler: no unused topic remains for a missing slot; stopping safely."); break
            original_topic = legacy["الموضوع"].strip(); angle = ANGLE_LIBRARY[index % len(ANGLE_LIBRARY)]
            source = legacy.get("المصادر القانونية", ""); category = "Content/PostBank"; fmt = ""; objective = ""; source_label = "Content/PostBank fallback"
        else:
            original_topic = brief["topic"].strip(); angle = brief["angle"].strip(); source = brief["legal_sources"].strip(); category = brief["category"]; fmt = brief["format"]; objective = brief["objective"]; source_label = "500-Topic-Bank"
        row = {"ID": f"{publish_date.replace('-', '')}-{posting_time.replace(':', '')}-R{index + 1:03d}", "الموضوع": f"{original_topic} — زاوية جديدة: {angle}", "تاريخ النشر": publish_date, "ساعة النشر": posting_time, "نوع الجدولة": "DATE_TIME", "الحالة": "READY", "المصادر القانونية": source, "ملاحظات": brief_notes(current_key, {"topic": original_topic, "category": category, "angle": angle, "format": fmt, "objective": objective}, posting_time, source_label)}
        used_topics.add(normalize_topic(original_topic)); insert_row_at_top(service, spreadsheet_id, sheet_name, row); created += 1
    print(f"Monthly recycler: created {created} missing rows for {current_key}; target = 11:00 and 19:00 Cairo time.")
    return migrated + replaced + created


topic_pool_for_month = _topic_pool_for_month
