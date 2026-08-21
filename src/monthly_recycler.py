from __future__ import annotations

import hashlib
from calendar import monthrange
from datetime import date

from src.post_bank import get_bank_rows
from src.sheets import get_values, insert_row_at_top, row_to_dict, update_row
from src.topic_bank_500 import TOPIC_BANK
from src.utils import parse_date

RECYCLE_MARKER = "MONTHLY_RECYCLE"
POSTING_TIMES = ("11:00", "19:00")

CATEGORY_ORDER = (
    "القانون الجنائي",
    "قانون الشركات والاستثمار",
    "قانون الأسرة",
    "قانون العمل الجديد",
    "القانون الإداري",
)

ANGLE_LIBRARY = [
    "خطأ شائع يقع فيه الناس وكيف يتجنبونه",
    "موقف واقعي قصير وما التصرف القانوني الصحيح",
    "متى يكون الحق ثابتًا ومتى قد يضيع؟",
    "أهم مستند أو دليل يحمي صاحب الحق",
    "ماذا تفعل خلال أول 24 ساعة من المشكلة؟",
    "الفرق بين التصور الشائع والحقيقة القانونية",
    "3 علامات تحذيرية قبل اتخاذ القرار",
    "متى تحتاج لمحامٍ ومتى يمكن اتخاذ خطوة أولية بنفسك؟",
    "أكثر سؤال يتكرر حول الموضوع وإجابته العملية",
    "كيف تنظر المحكمة عادةً للمشكلة بصورة مبسطة؟",
    "خطوة تبدو صحيحة لكنها قد تضر بموقفك",
    "مقارنة بين تصرفين ونتيجة كل منهما",
    "سيناريو عائلي أو عملي شائع مرتبط بالموضوع",
    "ما الذي يجب ألا توقع عليه أو تتنازل عنه؟",
    "Checklist عملية قبل بدء أي إجراء",
    "زاوية جديدة تركز على الوقاية قبل وقوع المشكلة",
]


def _month_key(value: str) -> str:
    try:
        return parse_date(value).strftime("%Y-%m")
    except Exception:
        return ""


def _posting_days(year: int, month: int, start_day: int) -> list[int]:
    return list(range(start_day, monthrange(year, month)[1] + 1))


def _normalize_topic(value: str) -> str:
    text = " ".join((value or "").split()).strip()
    if " — زاوية جديدة:" in text:
        text = text.split(" — زاوية جديدة:", 1)[0].strip()
    return text.casefold()


def _is_published(row: dict[str, str]) -> bool:
    status = row.get("الحالة", "").strip().upper()
    facebook_status = row.get("Facebook Status", "").strip().upper()
    linkedin_status = row.get("LinkedIn Status", "").strip().upper()
    return (
        status == "PUBLISHED"
        or facebook_status == "PUBLISHED"
        or linkedin_status == "PUBLISHED"
        or bool(row.get("Facebook Post ID", "").strip())
        or bool(row.get("LinkedIn Post ID", "").strip())
    )


def _historically_used_topics(values: list[list[str]], current_key: str) -> set[str]:
    """Build a permanent no-reuse set from all published history plus current-month assignments."""
    used: set[str] = set()
    marker = f"{RECYCLE_MARKER}:{current_key}"
    for raw in values[1:]:
        row = row_to_dict(raw)
        topic = row.get("الموضوع", "").strip()
        notes = row.get("ملاحظات", "")
        if _is_published(row) or marker in notes:
            if topic:
                used.add(_normalize_topic(topic))
            prefix = "الموضوع الأصلي:"
            if prefix in notes:
                original = notes.split(prefix, 1)[1].split("|", 1)[0].strip()
                if original:
                    used.add(_normalize_topic(original))
    return used


def _source_rows(values: list[list[str]], bank_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in values[1:]:
        row = row_to_dict(raw)
        if RECYCLE_MARKER in row.get("ملاحظات", ""):
            continue
        topic = row.get("الموضوع", "").strip()
        key = _normalize_topic(topic)
        if key and key not in seen:
            seen.add(key)
            result.append(row)
    for bank in bank_rows:
        topic = bank.get("الموضوع", "").strip()
        key = _normalize_topic(topic)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append({"الموضوع": topic, "المصادر القانونية": bank.get("المصادر القانونية", "")})
    return result


def _prepared_slots(values: list[list[str]], month_key: str) -> set[tuple[str, str]]:
    prepared: set[tuple[str, str]] = set()
    marker = f"{RECYCLE_MARKER}:{month_key}"
    for raw in values[1:]:
        row = row_to_dict(raw)
        if marker not in row.get("ملاحظات", ""):
            continue
        if row.get("الحالة", "").strip().upper() == "CANCELLED":
            continue
        prepared.add((row.get("تاريخ النشر", "").strip(), row.get("ساعة النشر", "").strip()))
    return prepared


def _used_month_topics(values: list[list[str]], month_key: str) -> set[str]:
    return _historically_used_topics(values, month_key)


def _migrate_future_slots(service, spreadsheet_id: str, sheet_name: str, values: list[list[str]], current: date, month_key: str) -> int:
    marker = f"{RECYCLE_MARKER}:{month_key}"
    desired: set[tuple[str, str]] = set()
    candidates: list[tuple[int, dict[str, str]]] = []
    for row_number, raw in enumerate(values[1:], start=2):
        row = row_to_dict(raw)
        if marker not in row.get("ملاحظات", ""):
            continue
        publish_date = row.get("تاريخ النشر", "").strip()
        publish_time = row.get("ساعة النشر", "").strip()
        if not publish_date or not publish_time:
            continue
        if publish_date < current.isoformat() or _is_published(row):
            continue
        status = row.get("الحالة", "").strip().upper()
        if status == "CANCELLED":
            continue
        if publish_time in POSTING_TIMES:
            desired.add((publish_date, publish_time))
        else:
            candidates.append((row_number, row))
    changed = 0
    for row_number, row in candidates:
        publish_date = row.get("تاريخ النشر", "").strip()
        old_time = row.get("ساعة النشر", "").strip()
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


def _topic_pool_for_month(month_key: str, used_topics: set[str]) -> list[dict[str, str]]:
    seed = int(hashlib.sha256(month_key.encode("utf-8")).hexdigest()[:8], 16)
    pools: dict[str, list[dict[str, str]]] = {category: [] for category in CATEGORY_ORDER}
    for item in TOPIC_BANK:
        if _normalize_topic(item["topic"]) not in used_topics:
            pools[item["category"]].append(item)
    for offset, category in enumerate(CATEGORY_ORDER):
        items = pools[category]
        if items:
            rotation = (seed + offset * 17) % len(items)
            pools[category] = items[rotation:] + items[:rotation]
    category_start = seed % len(CATEGORY_ORDER)
    sequence: list[dict[str, str]] = []
    indexes = {category: 0 for category in CATEGORY_ORDER}
    while len(sequence) < len(TOPIC_BANK):
        added = False
        for step in range(len(CATEGORY_ORDER)):
            category = CATEGORY_ORDER[(category_start + step) % len(CATEGORY_ORDER)]
            index = indexes[category]
            if index >= len(pools[category]):
                continue
            sequence.append(pools[category][index])
            indexes[category] += 1
            added = True
        if not added:
            break
    return sequence


def _brief_notes(current_key: str, brief: dict[str, str], posting_time: str, source: str = "500-Topic-Bank") -> str:
    return (
        f"{RECYCLE_MARKER}:{current_key} | الموضوع الأصلي: {brief['topic'].strip()} | "
        f"القسم: {brief['category']} | زاوية: {brief['angle'].strip()} | الصيغة: {brief['format'].strip()} | "
        f"الهدف: {brief['objective'].strip()} | Slot: {posting_time} | المصدر: {source} | "
        "لا يعاد استخدام موضوع منشور سابقًا أو نفس الموضوع بزاوية أخرى | ساعة النشر مثبتة تلقائيًا"
    )


def _replace_remaining_current_month_slots(service, spreadsheet_id: str, sheet_name: str, values: list[list[str]], current: date, current_key: str, topic_pool: list[dict[str, str]]) -> int:
    """Replace every remaining current-month unpublished slot, regardless of its original source."""
    historical_used = _historically_used_topics(values, current_key)
    replacements: list[tuple[int, dict[str, str]]] = []
    for row_number, raw in enumerate(values[1:], start=2):
        row = row_to_dict(raw)
        publish_date = row.get("تاريخ النشر", "").strip()
        posting_time = row.get("ساعة النشر", "").strip()
        if not publish_date or publish_date < current.isoformat() or posting_time not in POSTING_TIMES:
            continue
        if _is_published(row) or row.get("الحالة", "").strip().upper() in {"CANCELLED", "PARTIAL_FAILED"}:
            continue
        replacements.append((row_number, row))

    if not replacements:
        return 0

    available = [item for item in topic_pool if _normalize_topic(item["topic"]) not in historical_used]
    changed = 0
    for index, (row_number, row) in enumerate(replacements):
        if index >= len(available):
            print("Monthly recycler: 500-topic bank has no further never-published topic for a remaining slot.")
            break
        brief = available[index]
        historical_used.add(_normalize_topic(brief["topic"]))
        posting_time = row.get("ساعة النشر", "").strip()
        update_row(
            service,
            spreadsheet_id,
            sheet_name,
            row_number,
            {
                "الموضوع": f"{brief['topic'].strip()} — زاوية جديدة: {brief['angle'].strip()}",
                "المصادر القانونية": brief["legal_sources"].strip(),
                "الحالة": "READY",
                "آخر خطأ": "",
                "ملاحظات": _brief_notes(current_key, brief, posting_time, "500-Topic-Bank replacement"),
            },
        )
        changed += 1

    print(f"Monthly recycler: replaced {changed} remaining current-month unpublished slots with never-published bank topics.")
    return changed


def _legacy_source_for_slot(source_rows: list[dict[str, str]], index: int, used_topics: set[str]) -> dict[str, str] | None:
    if not source_rows:
        return None
    for offset in range(len(source_rows)):
        candidate = source_rows[(index + offset) % len(source_rows)]
        if _normalize_topic(candidate.get("الموضوع", "")) not in used_topics:
            return candidate
    return None


def recycle_month_if_needed(*, service, spreadsheet_id: str, sheet_name: str, current: date) -> int:
    values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")
    bank_rows = get_bank_rows(service, spreadsheet_id)
    current_key = current.strftime("%Y-%m")
    migrated = _migrate_future_slots(service, spreadsheet_id, sheet_name, values, current, current_key)
    if migrated:
        values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")

    historical_used = _historically_used_topics(values, current_key)
    source_rows = _source_rows(values, bank_rows)
    topic_pool = _topic_pool_for_month(current_key, historical_used)
    replaced = _replace_remaining_current_month_slots(service, spreadsheet_id, sheet_name, values, current, current_key, topic_pool)
    if replaced:
        values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")
        historical_used = _historically_used_topics(values, current_key)
        topic_pool = _topic_pool_for_month(current_key, historical_used)

    days = _posting_days(current.year, current.month, current.day)
    expected_slots = {(f"{current.year:04d}-{current.month:02d}-{day:02d}", posting_time) for day in days for posting_time in POSTING_TIMES}
    prepared = _prepared_slots(values, current_key)
    missing_slots = sorted(expected_slots - prepared)
    if not missing_slots:
        print(f"Monthly recycler: {current_key} is fully prepared for 11:00 and 19:00 Cairo time.")
        return migrated + replaced

    print(f"Monthly recycler: creating {len(missing_slots)} missing slots for {current_key}.")
    print(f"Monthly recycler: 500-topic bank active; {len(topic_pool)} never-published topics available.")
    created = 0
    used_topics = _historically_used_topics(values, current_key)
    bank_index = 0
    for index, (publish_date, posting_time) in enumerate(missing_slots):
        brief = None
        while bank_index < len(topic_pool):
            candidate = topic_pool[bank_index]
            bank_index += 1
            if _normalize_topic(candidate["topic"]) not in used_topics:
                brief = candidate
                break
        if brief is None:
            legacy = _legacy_source_for_slot(source_rows, index, used_topics)
            if legacy is None:
                print("Monthly recycler: no unused topic remains for a missing slot; stopping safely.")
                break
            original_topic = legacy["الموضوع"].strip()
            angle = ANGLE_LIBRARY[index % len(ANGLE_LIBRARY)]
            row = {"ID": f"{publish_date.replace('-', '')}-{posting_time.replace(':', '')}-R{index + 1:03d}", "الموضوع": f"{original_topic} — زاوية جديدة: {angle}", "تاريخ النشر": publish_date, "ساعة النشر": posting_time, "نوع الجدولة": "DATE_TIME", "الحالة": "READY", "المصادر القانونية": legacy.get("المصادر القانونية", ""), "ملاحظات": f"{RECYCLE_MARKER}:{current_key} | الموضوع الأصلي: {original_topic} | زاوية: {angle} | Slot: {posting_time} | المصدر: Content/PostBank fallback | ساعة النشر مثبتة تلقائيًا"}
            used_topics.add(_normalize_topic(original_topic))
        else:
            original_topic = brief["topic"].strip()
            row = {"ID": f"{publish_date.replace('-', '')}-{posting_time.replace(':', '')}-R{index + 1:03d}", "الموضوع": f"{original_topic} — زاوية جديدة: {brief['angle'].strip()}", "تاريخ النشر": publish_date, "ساعة النشر": posting_time, "نوع الجدولة": "DATE_TIME", "الحالة": "READY", "المصادر القانونية": brief["legal_sources"].strip(), "ملاحظات": _brief_notes(current_key, brief, posting_time)}
            used_topics.add(_normalize_topic(original_topic))
        insert_row_at_top(service, spreadsheet_id, sheet_name, row)
        created += 1

    print(f"Monthly recycler: created {created} missing rows for {current_key}; target = 11:00 and 19:00 Cairo time.")
    return migrated + replaced + created
