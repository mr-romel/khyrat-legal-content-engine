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
    return [day for day in range(start_day, monthrange(year, month)[1] + 1)]


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


def _already_recycled(values: list[list[str]], month_key: str) -> bool:
    marker = f"{RECYCLE_MARKER}:{month_key}"
    return any(marker in row_to_dict(raw).get("ملاحظات", "") for raw in values[1:])


def recycle_month_if_needed(*, service, spreadsheet_id: str, sheet_name: str, current: date) -> int:
    values = get_values(service, spreadsheet_id, f"{sheet_name}!A:U")
    bank_rows = get_bank_rows(service, spreadsheet_id)
    current_key = current.strftime("%Y-%m")

    if _already_recycled(values, current_key):
        print(f"Monthly recycler: {current_key} is already prepared.")
        return 0

    sources = _source_rows(values, bank_rows)
    if not sources:
        print("Monthly recycler: no source topics found in Content or PostBank.")
        return 0

    days = _posting_days(current.year, current.month, current.day)
    required_posts = len(days) * len(POSTING_TIMES)
    available_topics = len(sources)

    print(
        f"Monthly recycler: {available_topics} source topics available for "
        f"{required_posts} posts ({len(POSTING_TIMES)} per day)."
    )

    if available_topics < required_posts:
        print("Monthly recycler: using round-robin topic reuse with unique angles.")

    created = 0
    for day_index, day in enumerate(days):
        for slot_index, posting_time in enumerate(POSTING_TIMES):
            index = day_index * len(POSTING_TIMES) + slot_index
            source = sources[index % available_topics]
            original_topic = source["الموضوع"].strip()
            angle = ANGLE_LIBRARY[index % len(ANGLE_LIBRARY)]
            recycled_topic = f"{original_topic} — زاوية جديدة: {angle}"
            row = {
                "ID": f"{current_key.replace('-', '')}-R{index + 1:03d}",
                "الموضوع": recycled_topic,
                "تاريخ النشر": f"{current.year:04d}-{current.month:02d}-{day:02d}",
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
        f"Monthly recycler: created {created} rows for {current_key}; "
        "two publishing slots per day: 14:00 and 20:00 Cairo time."
    )
    return created
