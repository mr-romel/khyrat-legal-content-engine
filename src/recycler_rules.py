from __future__ import annotations

from calendar import monthrange

from src.sheets import row_to_dict
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


def month_key(value: str) -> str:
    try:
        return parse_date(value).strftime("%Y-%m")
    except Exception:
        return ""


def posting_days(year: int, month: int, start_day: int) -> list[int]:
    return list(range(start_day, monthrange(year, month)[1] + 1))


def normalize_topic(value: str) -> str:
    text = " ".join((value or "").split()).strip()
    if " — زاوية جديدة:" in text:
        text = text.split(" — زاوية جديدة:", 1)[0].strip()
    return text.casefold()


def is_published(row: dict[str, str]) -> bool:
    status = row.get("الحالة", "").strip().upper()
    facebook_status = row.get("Facebook Status", "").strip().upper()
    linkedin_status = row.get("LinkedIn Status", "").strip().upper()
    return (
        status == "PUBLISHED" or facebook_status == "PUBLISHED" or linkedin_status == "PUBLISHED"
        or bool(row.get("Facebook Post ID", "").strip()) or bool(row.get("LinkedIn Post ID", "").strip())
    )


def historically_used_topics(values: list[list[str]], current_key: str) -> set[str]:
    used: set[str] = set()
    marker = f"{RECYCLE_MARKER}:{current_key}"
    for raw in values[1:]:
        row = row_to_dict(raw)
        topic = row.get("الموضوع", "").strip()
        notes = row.get("ملاحظات", "")
        if is_published(row) or marker in notes:
            if topic:
                used.add(normalize_topic(topic))
            prefix = "الموضوع الأصلي:"
            if prefix in notes:
                original = notes.split(prefix, 1)[1].split("|", 1)[0].strip()
                if original:
                    used.add(normalize_topic(original))
    return used


def source_rows(values: list[list[str]], bank_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in values[1:]:
        row = row_to_dict(raw)
        if RECYCLE_MARKER in row.get("ملاحظات", ""):
            continue
        topic = row.get("الموضوع", "").strip()
        key = normalize_topic(topic)
        if key and key not in seen:
            seen.add(key)
            result.append(row)
    for bank in bank_rows:
        topic = bank.get("الموضوع", "").strip()
        key = normalize_topic(topic)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append({"الموضوع": topic, "المصادر القانونية": bank.get("المصادر القانونية", "")})
    return result


def prepared_slots(values: list[list[str]], month_key_value: str) -> set[tuple[str, str]]:
    prepared: set[tuple[str, str]] = set()
    marker = f"{RECYCLE_MARKER}:{month_key_value}"
    for raw in values[1:]:
        row = row_to_dict(raw)
        if marker not in row.get("ملاحظات", ""):
            continue
        if row.get("الحالة", "").strip().upper() == "CANCELLED":
            continue
        prepared.add((row.get("تاريخ النشر", "").strip(), row.get("ساعة النشر", "").strip()))
    return prepared


def brief_notes(current_key: str, brief: dict[str, str], posting_time: str, source: str = "500-Topic-Bank") -> str:
    return (
        f"{RECYCLE_MARKER}:{current_key} | الموضوع الأصلي: {brief['topic'].strip()} | "
        f"القسم: {brief['category']} | زاوية: {brief['angle'].strip()} | الصيغة: {brief['format'].strip()} | "
        f"الهدف: {brief['objective'].strip()} | Slot: {posting_time} | المصدر: {source} | "
        "لا يعاد استخدام موضوع منشور سابقًا أو نفس الموضوع بزاوية أخرى | ساعة النشر مثبتة تلقائيًا"
    )


def legacy_source_for_slot(source_rows_list: list[dict[str, str]], index: int, used_topics: set[str]) -> dict[str, str] | None:
    if not source_rows_list:
        return None
    for offset in range(len(source_rows_list)):
        candidate = source_rows_list[(index + offset) % len(source_rows_list)]
        if normalize_topic(candidate.get("الموضوع", "")) not in used_topics:
            return candidate
    return None
