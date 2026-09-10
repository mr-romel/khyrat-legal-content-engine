from __future__ import annotations

from datetime import date

from daily_schedule import daily_posting_times
from post_bank import get_bank_rows
from sheets import get_values, insert_row_at_top, row_to_dict, update_row
from recycler_rules import (
    ANGLE_LIBRARY,
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


def _target_slots(current: date) -> set[tuple[str, str]]:
    return {
        (f"{current.year:04d}-{current.month:02d}-{day:02d}", time)
        for day in posting_days(current.year, current.month, current.day)
        for time in daily_posting_times(current.year, current.month, day)
    }


def _migrate_future_slots(service, spreadsheet_id, sheet_name, values, current, month_key):
    marker = f"{RECYCLE_MARKER}:{month_key}"
    grouped: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for row_number, raw in enumerate(values[1:], start=2):
        row = row_to_dict(raw)
        if marker not in row.get("ملاحظات", "") or is_published(row):
            continue
        publish_date = row.get("تاريخ النشر", "").strip()
        publish_time = row.get("ساعة النشر", "").strip()
        if not publish_date or publish_date < current.isoformat() or not publish_time:
            continue
        if row.get("الحالة", "").strip().upper() == "CANCELLED":
            continue
        grouped.setdefault(publish_date, []).append((row_number, row))

    changed = 0
    for publish_date, entries in grouped.items():
        year, month, day = (int(part) for part in publish_date.split("-"))
        targets = list(daily_posting_times(year, month, day))
        occupied = set()
        kept_target = False
        for row_number, row in entries:
            old_time = row.get("ساعة النشر", "").strip()
            if old_time in targets and not kept_target:
                occupied.add(old_time)
                kept_target = True
                continue
            missing = [time for time in targets if time not in occupied]
            notes = row.get("ملاحظات", "")
            if missing:
                target_time = missing[0]
                update_row(service, spreadsheet_id, sheet_name, row_number, {
                    "ساعة النشر": target_time,
                    "الحالة": "READY",
                    "ملاحظات": f"{notes} | تم توحيد الموعد إلى {target_time} بتوقيت القاهرة وفق جدول منشور واحد يوميًا.",
                })
                occupied.add(target_time)
            else:
                update_row(service, spreadsheet_id, sheet_name, row_number, {
                    "الحالة": "CANCELLED",
                    "ملاحظات": f"{notes} | تم إلغاء slot زائد بعد اعتماد منشور واحد فقط لليوم {publish_date}.",
                })
            changed += 1
    if changed:
        print(f"Monthly recycler: normalized {changed} future rows to one variable Cairo slot per day.")
    return changed


def _replace_remaining_current_month_slots(service, spreadsheet_id, sheet_name, values, current, current_key, topic_pool):
    historical_used = historically_used_topics(values, current_key)
    marker = f"{RECYCLE_MARKER}:{current_key}"
    target_slots = _target_slots(current)
    replacements = []
    for row_number, raw in enumerate(values[1:], start=2):
        row = row_to_dict(raw)
        slot = (row.get("تاريخ النشر", "").strip(), row.get("ساعة النشر", "").strip())
        if slot not in target_slots or marker in row.get("ملاحظات", ""):
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
        update_row(service, spreadsheet_id, sheet_name, row_number, {
            "الموضوع": f"{brief['topic'].strip()} — زاوية جديدة: {brief['angle'].strip()}",
            "المصادر القانونية": brief["legal_sources"].strip(),
            "الحالة": "READY",
            "آخر خطأ": "",
            "ملاحظات": brief_notes(current_key, brief, row.get("ساعة النشر", "").strip(), "500-Topic-Bank replacement"),
        })
        changed += 1
    print(f"Monthly recycler: replaced {changed} remaining current-month unpublished target slots.")
    return changed


def base_topic_key(value: str) -> str:
    text = normalize_topic(value)
    parts = [part.strip() for part in text.split(" — ") if part.strip()]
    return parts[0] if parts else text


def _recent_published_signature(values: list[list[str]], current_key: str) -> tuple[str, str, str]:
    latest = ("", "", "")
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


def _select_next_brief(topic_pool, used_topics, used_bases, recent_signature=("", "", "")):
    used = {normalize_topic(value) for value in (used_topics or set())}
    bases = {str(value).strip().casefold() for value in (used_bases or set()) if str(value).strip()}
    recent_base, recent_category, recent_angle = (str(v).strip().casefold() for v in recent_signature)
    candidates = [
        brief for brief in topic_pool
        if normalize_topic(brief["topic"]) not in used and brief["topic"].strip().casefold() not in bases
    ]
    if not candidates:
        candidates = [brief for brief in topic_pool if normalize_topic(brief["topic"]) not in used]
    if not candidates:
        return None

    def penalty(brief):
        return (
            int(brief["topic"].strip().casefold() == recent_base) * 1000
            + int(brief.get("category", "").strip().casefold() == recent_category) * 100
            + int(brief.get("angle", "").strip().casefold() == recent_angle) * 50
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

    expected_slots = _target_slots(current)
    prepared = prepared_slots(values, current_key)
    missing_slots = sorted(expected_slots - prepared)
    if not missing_slots:
        print(f"Monthly recycler: {current_key} has exactly one variable slot per day from 10:00 through 22:00 Cairo time.")
        return migrated + replaced

    print(f"Monthly recycler: creating {len(missing_slots)} missing variable slots for {current_key}.")
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
            topic = brief["topic"].strip(); angle = brief["angle"].strip(); source = brief["legal_sources"].strip()
            category, fmt, objective = brief["category"], brief["format"], brief["objective"]
            source_label = "500-Topic-Bank adaptive rotation"
            topic_pool.remove(brief)
        else:
            legacy = legacy_source_for_slot(source_rows_list, index, used_topics)
            if legacy is None:
                topic_pool = adaptive_topic_pool(current_key, set(), {c: 0 for c in historically_used_categories(values, current_key)}, {a: 0 for a in ANGLE_LIBRARY})
                brief = _select_next_brief(topic_pool, set(), set(), recent_signature)
                if not brief:
                    break
                topic = brief["topic"].strip(); angle = brief["angle"].strip(); source = brief["legal_sources"].strip()
                category, fmt, objective = brief["category"], brief["format"], brief["objective"]
                source_label = "500-Topic-Bank new cycle"
                topic_pool.remove(brief)
            else:
                topic = legacy["الموضوع"].strip(); angle = ANGLE_LIBRARY[index % len(ANGLE_LIBRARY)]
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
        used_topics.add(normalize_topic(topic)); used_bases.add(topic.casefold())
        category_counts[category] = category_counts.get(category, 0) + 1
        angle_counts[angle] = angle_counts.get(angle, 0) + 1
        recent_signature = (topic.casefold(), category, angle)
        topic_pool = adaptive_topic_pool(current_key, used_topics, category_counts, angle_counts)
        insert_row_at_top(service, spreadsheet_id, sheet_name, row)
        created += 1

    print(f"Monthly recycler: created {created} missing rows using the daily one-slot variable schedule.")
    return migrated + replaced + created


_topic_pool_for_month = topic_pool_for_month
