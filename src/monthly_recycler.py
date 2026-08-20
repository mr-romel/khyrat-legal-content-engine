from __future__ import annotations

from calendar import monthrange
from datetime import date

from src.post_bank import get_bank_rows
from src.sheets import get_values, insert_row_at_top, row_to_dict
from src.utils import parse_date

RECYCLE_MARKER = "MONTHLY_RECYCLE"
POSTING_TIMES = ("14:00", "20:00")

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


def _source_rows(values: list[list[str]], bank_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw in values[1:]:
        row = row_to_dict(raw)
        if RECYCLE_MARKER in row.get("ملاحظات", ""):
            continue
        topic = row.get("الموضوع", "").strip()
        if topic and topic not in seen:
            seen.add(topic)
            result.append(row)

    for bank in bank_rows:
        topic = bank.get("الموضوع", "").strip()
        if not topic or topic in seen:
            continue
        seen.add(topic)
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


def recycle_month_if_needed(*, service, spreadsheet_id: str, sheet_name: str, current: date) -> int:
    values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")
    bank_rows = get_bank_rows(service, spreadsheet_id)
    current_key = current.strftime("%Y-%m")

    sources = _source_rows(values, bank_rows)
    if not sources:
        print("Monthly recycler: no source topics found in Content or PostBank.")
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
        print(f"Monthly recycler: {current_key} is fully prepared for 14:00 and 20:00 Cairo time.")
        return 0

    print(
        f"Monthly recycler: {len(prepared)} slots already prepared; "
        f"creating {len(missing_slots)} missing slots for {current_key}."
    )

    if len(sources) < len(missing_slots):
        print("Monthly recycler: source topics are fewer than required slots; using round-robin reuse with unique angles.")

    created = 0
    for index, (publish_date, posting_time) in enumerate(missing_slots):
        source = sources[(len(prepared) + index) % len(sources)]
        original_topic = source["الموضوع"].strip()
        angle = ANGLE_LIBRARY[(len(prepared) + index) % len(ANGLE_LIBRARY)]
        recycled_topic = f"{original_topic} — زاوية جديدة: {angle}"
        row = {
            "ID": f"{publish_date.replace('-', '')}-{posting_time.replace(':', '')}-R{index + 1:03d}",
            "الموضوع": recycled_topic,
            "تاريخ النشر": publish_date,
            "ساعة النشر": posting_time,
            "نوع الجدولة": "DATE_TIME",
            "الحالة": "READY",
            "المصادر القانونية": source.get("المصادر القانونية", ""),
            "ملاحظات": (
                f"{RECYCLE_MARKER}:{current_key} | الموضوع الأصلي: {original_topic} | "
                f"زاوية: {angle} | Slot: {posting_time} | المصدر: Content/PostBank | "
                "ساعة النشر مثبتة تلقائيًا"
            ),
        }
        insert_row_at_top(service, spreadsheet_id, sheet_name, row)
        created += 1

    print(
        f"Monthly recycler: created {created} missing rows for {current_key}; "
        "target is two publishing slots every day: 14:00 and 20:00 Cairo time."
    )
    return created
