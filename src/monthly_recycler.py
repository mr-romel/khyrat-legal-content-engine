from __future__ import annotations

from datetime import date

from post_bank import get_bank_rows
from sheets import get_values, insert_row_at_top, row_to_dict, update_row
from topic_bank_500 import TOPIC_BANK
from recycler_rules import (
    ANGLE_LIBRARY,
    POSTING_TIMES,
    RECYCLE_MARKER,
    adaptive_topic_pool,
    brief_notes,
    historically_used_angles,
    historically_used_base_topics,
    historically_used_categories,
    historically_used_topics,
    is_published,
    legacy_source_for_slot,
    normalize_topic,
    posting_days,
    prepared_slots,
    source_rows,
    topic_pool_for_month,
)


def _migrate_future_slots(service, spreadsheet_id, sheet_name, values, current, month_key):
    marker = f"{RECYCLE_MARKER}:{month_key}"
    desired, candidates = set(), []
    for row_number, raw in enumerate(values[1:], start=2):
        row = row_to_dict(raw)
        if marker not in row.get("ملاحظات", ""):
            continue
        publish_date = row.get("تاريخ النشر", "").strip()
        publish_time = row.get("ساعة النشر", "").strip()
        if not publish_date or not publish_time or publish_date < current.isoformat() or is_published(row):
            continue
        if row.get("الحالة", "").strip().upper() == "CANCELLED":
            continue
        if publish_time in POSTING_TIMES:
            desired.add((publish_date, publish_time))
        else:
            candidates.append((row_number, row))
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
    if changed:
        print(f"Monthly recycler: migrated {changed} future legacy slots to 11:00/19:00.")
    return changed


def _replace_remaining_current_month_slots(service, spreadsheet_id, sheet_name, values, current, current_key, topic_pool):
    historical_used = historically_used_topics(values, current_key)
    marker = f"{RECYCLE_MARKER}:{current_key}"
    replacements = []
    for row_number, raw in enumerate(values[1:], start=2):
        row = row_to_dict(raw)
        publish_date = row.get("تاريخ النشر", "").strip()
        posting_time = row.get("ساعة النشر", "").strip()
        if not publish_date or publish_date < current.isoformat() or posting_time not in POSTING_TIMES or marker in row.get("ملاحظات", ""):
            continue
        if is_published(row) or row.get("الحالة", "").strip().upper() in {"CANCELLED", "PARTIAL_FAILED"}:
            continue
        replacements.append((row_number, row))

    available = [item for item in topic_pool if normalize_topic(item["topic"]) not in historical_used]
    used_bases = historically_used_base_topics(values, current_key)
    preferred = [item for item in available if item["topic"].strip().casefold() not in used_bases]
    ordered = preferred + [item for item in available if item not in preferred]

    changed = 0
    for index, (row_number, row) in enumerate(replacements):
        if index >= len(ordered):
            break
        brief = ordered[index]
        historical_used.add(normalize_topic(brief["topic"]))
        posting_time = row.get("ساعة النشر", "").strip()
        update_row(service, spreadsheet_id, sheet_name, row_number, {
            "الموضوع": f"{brief['topic'].strip()} — زاوية جديدة: {brief['angle'].strip()}",
            "المصادر القانونية": brief["legal_sources"].strip(),
            "الحالة": "READY",
            "آخر خطأ": "",
            "ملاحظات": brief_notes(current_key, brief, posting_time, "500-Topic-Bank replacement"),
        })
        changed += 1
    print(f"Monthly recycler: replaced {changed} remaining current-month unpublished slots with diverse bank topics.")
    return changed


def _recent_published_signature(values: list[list[str]], current_key: str) -> tuple[str, str, str]:
    """Return the latest published base topic/category/angle for adjacency avoidance."""
    marker = f"{RECYCLE_MARKER}:{current_key}"
    latest: tuple[str, str, str] = ("", "", "")
    for raw in values[1:]:
        row = row_to_dict(raw)
        if not is_published(row):
            continue
        topic = row.get("الموضوع", "").strip()
        if not topic:
            continue
        notes = row.get("ملاحظات", "")
        category = notes.split("القسم:", 1)[1].split("|", 1)[0].strip() if "القسم:" in notes else ""
        angle = notes.split("زاوية:", 1)[1].split("|", 1)[0].strip() if "زاوية:" in notes else ""
        latest = (base_topic_key(topic), category, angle)
    return latest


def base_topic_key(value: str) -> str:
    text = normalize_topic(value)
    parts = [part.strip() for part in text.split(" — ") if part.strip()]
    return parts[0] if parts else text


def _select_next_brief(topic_pool, used_topics, used_bases, recent_signature=("", "", "")):
    """Select an unused brief while strongly avoiding immediate topic/category/angle repetition."""
    used = {normalize_topic(value) for value in (used_topics or set())}
    bases = {str(value).strip().casefold() for value in (used_bases or set()) if str(value).strip()}
    recent_base, recent_category, recent_angle = (str(v).strip().casefold() for v in recent_signature)

    candidates = [
        brief for brief in topic_pool
        if normalize_topic(brief["topic"]) not in used
        and brief["topic"].strip().casefold() not in bases
    ]
    if not candidates:
        candidates = [brief for brief in topic_pool if normalize_topic(brief["topic"]) not in used]
    if not candidates:
        return None

    def penalty(brief):
        base = brief["topic"].strip().casefold()
        category = brief.get("category", "").strip().casefold()
        angle = brief.get("angle", "").strip().casefold()
        return (
            int(base == recent_base) * 1000
            + int(category == recent_category) * 100
            + int(angle == recent_angle) * 50
        )

    return min(candidates, key=lambda brief: (penalty(brief), brief["category"], brief["angle"], brief["topic"]))


def recycle_month_if_needed(*, service, spreadsheet_id: str, sheet_name: str, current: date) -> int:
    values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")
    bank_rows = get_bank_rows(service, spreadsheet_id)
    current_key = current.strftime("%Y-%m")
    migrated = _migrate_future_slots(service, spreadsheet_id, sheet_name, values, current, current_key)
    if migrated:
        values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")

    historical_used = historically_used_topics(values, current_key)
    topic_pool = topic_pool_for_month(current_key, historical_used)
    replaced = _replace_remaining_current_month_slots(service, spreadsheet_id, sheet_name, values, current, current_key, topic_pool)
    if replaced:
        values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")
        historical_used = historically_used_topics(values, current_key)
        topic_pool = topic_pool_for_month(current_key, historical_used)

    days = posting_days(current.year, current.month, current.day)
    expected_slots = {(f"{current.year:04d}-{current.month:02d}-{day:02d}", t) for day in days for t in POSTING_TIMES}
    prepared = prepared_slots(values, current_key)
    missing_slots = sorted(expected_slots - prepared)
    if not missing_slots:
        print(f"Monthly recycler: {current_key} is fully prepared for 11:00 and 19:00 Cairo time.")
        return migrated + replaced

    print(f"Monthly recycler: creating {len(missing_slots)} missing slots for {current_key}.")
    used_topics = historically_used_topics(values, current_key)
    used_bases = historically_used_base_topics(values, current_key)
    category_counts = historically_used_categories(values, current_key)
    angle_counts = historically_used_angles(values, current_key)
    topic_pool = adaptive_topic_pool(current_key, used_topics, category_counts, angle_counts)
    source_rows_list = source_rows(values, bank_rows)
    recent_signature = _recent_published_signature(values, current_key)
    created = 0
    for index, (publish_date, posting_time) in enumerate(missing_slots):
        brief = _select_next_brief(topic_pool, used_topics, used_bases, recent_signature)
        if brief:
            topic = brief["topic"].strip()
            angle = brief["angle"].strip()
            source = brief["legal_sources"].strip()
            category = brief["category"]
            fmt = brief["format"]
            objective = brief["objective"]
            source_label = "500-Topic-Bank adaptive rotation"
            topic_pool.remove(brief)
        else:
            legacy = legacy_source_for_slot(source_rows_list, index, used_topics)
            if legacy is None:
                print("Monthly recycler: no unused topic remains; starting a fresh 500-bank cycle.")
                topic_pool = adaptive_topic_pool(current_key, set(), {category: 0 for category in historically_used_categories(values, current_key)}, {angle: 0 for angle in ANGLE_LIBRARY})
                brief = _select_next_brief(topic_pool, set(), set(), recent_signature)
                if brief:
                    topic = brief["topic"].strip()
                    angle = brief["angle"].strip()
                    source = brief["legal_sources"].strip()
                    category = brief["category"]
                    fmt = brief["format"]
                    objective = brief["objective"]
                    source_label = "500-Topic-Bank new cycle"
                    topic_pool.remove(brief)
                else:
                    break
            else:
                topic = legacy["الموضوع"].strip()
                angle = ANGLE_LIBRARY[index % len(ANGLE_LIBRARY)]
                source = legacy.get("المصادر القانونية", "")
                category, fmt, objective, source_label = "Content/PostBank", "", "", "Content/PostBank fallback"

        row = {
            "ID": f"{publish_date.replace('-', '')}-{posting_time.replace(':', '')}-R{index + 1:03d}",
            "الموضوع": f"{topic} — زاوية جديدة: {angle}",
            "تاريخ النشر": publish_date,
            "ساعة النشر": posting_time,
            "نوع الجدولة": "DATE_TIME",
            "الحالة": "READY",
            "المصادر القانونية": source,
            "ملاحظات": brief_notes(current_key, {"topic": topic, "category": category, "angle": angle, "format": fmt, "objective": objective}, posting_time, source_label),
        }
        used_topics.add(normalize_topic(topic))
        used_bases.add(topic.casefold())
        category_counts[category] = category_counts.get(category, 0) + 1
        angle_counts[angle] = angle_counts.get(angle, 0) + 1
        recent_signature = (topic.casefold(), category, angle)
        topic_pool = adaptive_topic_pool(current_key, used_topics, category_counts, angle_counts)
        insert_row_at_top(service, spreadsheet_id, sheet_name, row)
        created += 1

    print(f"Monthly recycler: created {created} missing rows for {current_key}; target = 11:00 and 19:00 Cairo time.")
    return migrated + replaced + created


# Backward-compatible alias used by the existing quality gate.
_topic_pool_for_month = topic_pool_for_month
