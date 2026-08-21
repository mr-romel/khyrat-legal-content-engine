from __future__ import annotations

import hashlib
from calendar import monthrange
from datetime import date

from src.post_bank import get_bank_rows
from src.sheets import get_values, insert_row_at_top, row_to_dict
from src.topic_bank import TOPIC_BANK
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
        result.append({
            "الموضوع": topic,
            "المصادر القانونية": bank.get("المصادر القانونية", ""),
        })

    return result


def _prepared_slots(values: list[list[str]], month_key: str) -> set[tuple[str, str]]:
    prepared: set[tuple[str, str]] = set()
    marker = f"{RECYCLE_MARKER}:{month_key}"
    for raw in values[1:]:
        row = row_to_dict(raw)
        if marker not in row.get("ملاحظات", ""):
            continue
        prepared.add((row.get("تاريخ النشر", "").strip(), row.get("ساعة النشر", "").strip()))
    return prepared


def _used_month_topics(values: list[list[str]], month_key: str) -> set[str]:
    used: set[str] = set()
    marker = f"{RECYCLE_MARKER}:{month_key}"
    for raw in values[1:]:
        row = row_to_dict(raw)
        if marker not in row.get("ملاحظات", ""):
            continue
        topic = row.get("الموضوع", "").strip()
        if topic:
            used.add(_normalize_topic(topic))
        notes = row.get("ملاحظات", "")
        prefix = "الموضوع الأصلي:"
        if prefix in notes:
            original = notes.split(prefix, 1)[1].split("|", 1)[0].strip()
            if original:
                used.add(_normalize_topic(original))
    return used


def _topic_pool_for_month(month_key: str, used_topics: set[str]) -> list[dict[str, str]]:
    """Return a deterministic monthly sequence balanced across the five categories."""
    seed = int(hashlib.sha256(month_key.encode("utf-8")).hexdigest()[:8], 16)
    pools: dict[str, list[dict[str, str]]] = {category: [] for category in CATEGORY_ORDER}

    for item in TOPIC_BANK:
        if _normalize_topic(item["topic"]) not in used_topics:
            pools[item["category"]].append(item)

    # Rotate each category independently so the monthly sequence changes from month to month
    # without relying on non-deterministic random state.
    for offset, category in enumerate(CATEGORY_ORDER):
        items = pools[category]
        if not items:
            continue
        rotation = (seed + offset * 17) % len(items)
        pools[category] = items[rotation:] + items[:rotation]

    category_start = seed % len(CATEGORY_ORDER)
    sequence: list[dict[str, str]] = []
    indexes = {category: 0 for category in CATEGORY_ORDER}

    # Round-robin categories keeps the month diversified instead of posting one legal area
    # for several consecutive slots. The bank has 40 topics per category, enough for the
    # current month and multiple future cycles without immediate repetition.
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


def _legacy_source_for_slot(
    source_rows: list[dict[str, str]],
    index: int,
    used_topics: set[str],
) -> dict[str, str] | None:
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

    source_rows = _source_rows(values, bank_rows)
    topic_pool = _topic_pool_for_month(current_key, _used_month_topics(values, current_key))
    if not source_rows and not topic_pool:
        print("Monthly recycler: no source topics found in Content, PostBank, or the 200-topic bank.")
        return 0

    days = _posting_days(current.year, current.month, current.day)
    expected_slots = {
        (f"{current.year:04d}-{current.month:02d}-{day:02d}", posting_time)
        for day in days
        for posting_time in POSTING_TIMES
    }
    prepared = _prepared_slots(values, current_key)
    missing_slots = sorted(expected_slots - prepared)

    if not missing_slots:
        print(f"Monthly recycler: {current_key} is fully prepared for 11:00 and 19:00 Cairo time.")
        return 0

    print(
        f"Monthly recycler: {len(prepared)} slots already prepared; "
        f"creating {len(missing_slots)} missing slots for {current_key}."
    )
    print(f"Monthly recycler: 200-topic bank active; {len(topic_pool)} unused bank topics available for this month.")

    created = 0
    used_topics = _used_month_topics(values, current_key)
    bank_index = 0

    for index, (publish_date, posting_time) in enumerate(missing_slots):
        brief = None
        while bank_index < len(topic_pool):
            candidate = topic_pool[bank_index]
            bank_index += 1
            candidate_key = _normalize_topic(candidate["topic"])
            if candidate_key not in used_topics:
                brief = candidate
                break

        if brief is not None:
            original_topic = brief["topic"].strip()
            angle = brief["angle"].strip()
            recycled_topic = f"{original_topic} — زاوية جديدة: {angle}"
            legal_sources = brief["legal_sources"].strip()
            notes = (
                f"{RECYCLE_MARKER}:{current_key} | الموضوع الأصلي: {original_topic} | "
                f"القسم: {brief['category']} | زاوية: {angle} | الصيغة: {brief['format']} | "
                f"الهدف: {brief['objective']} | Slot: {posting_time} | المصدر: 200-Topic-Bank | "
                "ساعة النشر مثبتة تلقائيًا"
            )
            used_topics.add(_normalize_topic(original_topic))
        else:
            legacy = _legacy_source_for_slot(source_rows, index, used_topics)
            if legacy is None:
                print("Monthly recycler: no unused topic remains for a missing slot; stopping safely.")
                break
            original_topic = legacy["الموضوع"].strip()
            angle = ANGLE_LIBRARY[index % len(ANGLE_LIBRARY)]
            recycled_topic = f"{original_topic} — زاوية جديدة: {angle}"
            legal_sources = legacy.get("المصادر القانونية", "")
            notes = (
                f"{RECYCLE_MARKER}:{current_key} | الموضوع الأصلي: {original_topic} | "
                f"زاوية: {angle} | Slot: {posting_time} | المصدر: Content/PostBank fallback | "
                "ساعة النشر مثبتة تلقائيًا"
            )
            used_topics.add(_normalize_topic(original_topic))

        row = {
            "ID": f"{publish_date.replace('-', '')}-{posting_time.replace(':', '')}-R{index + 1:03d}",
            "الموضوع": recycled_topic,
            "تاريخ النشر": publish_date,
            "ساعة النشر": posting_time,
            "نوع الجدولة": "DATE_TIME",
            "الحالة": "READY",
            "المصادر القانونية": legal_sources,
            "ملاحظات": notes,
        }
        insert_row_at_top(service, spreadsheet_id, sheet_name, row)
        created += 1

    print(
        f"Monthly recycler: created {created} missing rows for {current_key}; "
        "source priority = 200-topic bank, then Content/PostBank fallback; "
        "target = two publishing slots every day at 11:00 and 19:00 Cairo time."
    )
    return created
