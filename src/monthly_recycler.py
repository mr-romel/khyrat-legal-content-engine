from __future__ import annotations

from calendar import monthrange
from datetime import date

from src.sheets import get_values, insert_row_at_top, row_to_dict
from src.utils import parse_date

RECYCLE_MARKER = "MONTHLY_RECYCLE"
DEFAULT_POSTING_TIME = "14:00"

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


def _even_days(year: int, month: int) -> list[int]:
    return [
        day
        for day in range(1, monthrange(year, month)[1] + 1)
        if day % 2 == 0
    ]


def _previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _source_rows(values: list[list[str]], previous_key: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw in values[1:]:
        row = row_to_dict(raw)
        if _month_key(row.get("تاريخ النشر", "")) != previous_key:
            continue
        if row.get("الحالة", "").strip().upper() != "PUBLISHED":
            continue

        topic = row.get("الموضوع", "").strip()
        if not topic or topic in seen:
            continue

        seen.add(topic)
        result.append(row)

    return result


def _already_recycled(values: list[list[str]], month_key: str) -> bool:
    marker = f"{RECYCLE_MARKER}:{month_key}"
    return any(
        marker in row_to_dict(raw).get("ملاحظات", "")
        for raw in values[1:]
    )


def recycle_month_if_needed(
    *,
    service,
    spreadsheet_id: str,
    sheet_name: str,
    current: date,
) -> int:
    """Create the current month's recycled queue once and self-heal if day 1 was missed."""
    values = get_values(
        service,
        spreadsheet_id,
        f"{sheet_name}!A:U",
    )

    current_key = current.strftime("%Y-%m")
    if _already_recycled(values, current_key):
        print(f"Monthly recycler: {current_key} is already prepared.")
        return 0

    previous_year, previous_month = _previous_month(
        current.year,
        current.month,
    )
    previous_key = f"{previous_year:04d}-{previous_month:02d}"
    sources = _source_rows(values, previous_key)

    if not sources:
        print(
            "Monthly recycler: no published source rows found for "
            f"{previous_key}."
        )
        return 0

    days = [
        day
        for day in _even_days(current.year, current.month)
        if day >= current.day
    ]

    if not days:
        return 0

    created = 0
    for index, day in enumerate(days):
        source = sources[index % len(sources)]
        original_topic = source["الموضوع"].strip()
        angle = ANGLE_LIBRARY[index % len(ANGLE_LIBRARY)]
        recycled_topic = f"{original_topic} — زاوية جديدة: {angle}"

        row = {
            "ID": f"{current_key.replace('-', '')}-R{index + 1:02d}",
            "الموضوع": recycled_topic,
            "تاريخ النشر": f"{current.year:04d}-{current.month:02d}-{day:02d}",
            "ساعة النشر": DEFAULT_POSTING_TIME,
            "نوع الجدولة": "DATE_TIME",
            "الحالة": "READY",
            "المصادر القانونية": source.get("المصادر القانونية", ""),
            "ملاحظات": (
                f"{RECYCLE_MARKER}:{current_key} | "
                f"الموضوع الأصلي: {original_topic} | "
                f"زاوية: {angle} | "
                "تم إنشاء النسخة الجديدة دون تعديل صف الشهر السابق | "
                f"ساعة النشر مثبتة تلقائيًا: {DEFAULT_POSTING_TIME}"
            ),
        }

        insert_row_at_top(
            service,
            spreadsheet_id,
            sheet_name,
            row,
        )
        created += 1

    print(f"Monthly recycler: created {created} rows for {current_key} at {DEFAULT_POSTING_TIME} Cairo time.")
    return created
