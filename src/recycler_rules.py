from __future__ import annotations

import hashlib
from calendar import monthrange

from sheets import row_to_dict
from topic_bank_500 import TOPIC_BANK
from utils import parse_date

RECYCLE_MARKER = "MONTHLY_RECYCLE"
POSTING_TIMES = ("11:00", "19:00")
CATEGORY_ORDER = ("القانون الجنائي", "قانون الشركات والاستثمار", "قانون الأسرة", "قانون العمل الجديد", "القانون الإداري")
ANGLE_LIBRARY = [
    "خطأ شائع يقع فيه الناس وكيف يتجنبونه", "موقف واقعي قصير وما التصرف القانوني الصحيح",
    "متى يكون الحق ثابتًا ومتى قد يضيع؟", "أهم مستند أو دليل يحمي صاحب الحق",
    "ماذا تفعل خلال أول 24 ساعة من المشكلة؟", "الفرق بين التصور الشائع والحقيقة القانونية",
    "3 علامات تحذيرية قبل اتخاذ القرار", "متى تحتاج لمحامٍ ومتى يمكن اتخاذ خطوة أولية بنفسك؟",
    "أكثر سؤال يتكرر حول الموضوع وإجابته العملية", "كيف تنظر المحكمة عادةً للمشكلة بصورة مبسطة؟",
    "خطوة تبدو صحيحة لكنها قد تضر بموقفك", "مقارنة بين تصرفين ونتيجة كل منهما",
    "سيناريو عائلي أو عملي شائع مرتبط بالموضوع", "ما الذي يجب ألا توقع عليه أو تتنازل عنه؟",
    "Checklist عملية قبل بدء أي إجراء", "زاوية جديدة تركز على الوقاية قبل وقوع المشكلة",
]

def month_key(value: str) -> str:
    try: return parse_date(value).strftime("%Y-%m")
    except Exception: return ""

def posting_days(year: int, month: int, start_day: int) -> list[int]:
    return list(range(start_day, monthrange(year, month)[1] + 1))

def normalize_topic(value: str) -> str:
    text = " ".join((value or "").split()).strip()
    if " — زاوية جديدة:" in text: text = text.split(" — زاوية جديدة:", 1)[0].strip()
    return text.casefold()

def is_published(row: dict[str, str]) -> bool:
    status = row.get("الحالة", "").strip().upper()
    return status == "PUBLISHED" or row.get("Facebook Status", "").strip().upper() == "PUBLISHED" or row.get("LinkedIn Status", "").strip().upper() == "PUBLISHED" or bool(row.get("Facebook Post ID", "").strip()) or bool(row.get("LinkedIn Post ID", "").strip())

def historically_used_topics(values: list[list[str]], current_key: str) -> set[str]:
    used = set(); marker = f"{RECYCLE_MARKER}:{current_key}"
    for raw in values[1:]:
        row = row_to_dict(raw); topic = row.get("الموضوع", "").strip(); notes = row.get("ملاحظات", "")
        if is_published(row) or marker in notes:
            if topic: used.add(normalize_topic(topic))
            if "الموضوع الأصلي:" in notes:
                original = notes.split("الموضوع الأصلي:", 1)[1].split("|", 1)[0].strip()
                if original: used.add(normalize_topic(original))
    return used

def source_rows(values: list[list[str]], bank_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result, seen = [], set()
    for raw in values[1:]:
        row = row_to_dict(raw); topic = row.get("الموضوع", "").strip(); key = normalize_topic(topic)
        if RECYCLE_MARKER not in row.get("ملاحظات", "") and key and key not in seen: seen.add(key); result.append(row)
    for bank in bank_rows:
        topic = bank.get("الموضوع", "").strip(); key = normalize_topic(topic)
        if key and key not in seen: seen.add(key); result.append({"الموضوع": topic, "المصادر القانونية": bank.get("المصادر القانونية", "")})
    return result

def prepared_slots(values: list[list[str]], month_key_value: str) -> set[tuple[str, str]]:
    marker = f"{RECYCLE_MARKER}:{month_key_value}"; result = set()
    for raw in values[1:]:
        row = row_to_dict(raw)
        if marker in row.get("ملاحظات", "") and row.get("الحالة", "").strip().upper() != "CANCELLED": result.add((row.get("تاريخ النشر", "").strip(), row.get("ساعة النشر", "").strip()))
    return result

def brief_notes(current_key: str, brief: dict[str, str], posting_time: str, source: str = "500-Topic-Bank") -> str:
    return f"{RECYCLE_MARKER}:{current_key} | الموضوع الأصلي: {brief['topic'].strip()} | القسم: {brief['category']} | زاوية: {brief['angle'].strip()} | الصيغة: {brief['format'].strip()} | الهدف: {brief['objective'].strip()} | Slot: {posting_time} | المصدر: {source} | لا يعاد استخدام موضوع منشور سابقًا أو نفس الموضوع بزاوية أخرى | ساعة النشر مثبتة تلقائيًا"

def legacy_source_for_slot(source_rows_list: list[dict[str, str]], index: int, used_topics: set[str]) -> dict[str, str] | None:
    if not source_rows_list: return None
    for offset in range(len(source_rows_list)):
        candidate = source_rows_list[(index + offset) % len(source_rows_list)]
        if normalize_topic(candidate.get("الموضوع", "")) not in used_topics: return candidate
    return None

def topic_pool_for_month(current_key: str, used_topics: set[str]) -> list[dict[str, str]]:
    seed = int(hashlib.sha256(current_key.encode("utf-8")).hexdigest()[:8], 16); pools = {c: [] for c in CATEGORY_ORDER}
    for item in TOPIC_BANK:
        if normalize_topic(item["topic"]) not in used_topics: pools[item["category"]].append(item)
    for offset, category in enumerate(CATEGORY_ORDER):
        items = pools[category]
        if items:
            rotation = (seed + offset * 17) % len(items); pools[category] = items[rotation:] + items[:rotation]
    start = seed % len(CATEGORY_ORDER); indexes = {c: 0 for c in CATEGORY_ORDER}; sequence = []
    while len(sequence) < len(TOPIC_BANK):
        added = False
        for step in range(len(CATEGORY_ORDER)):
            category = CATEGORY_ORDER[(start + step) % len(CATEGORY_ORDER)]
            if indexes[category] < len(pools[category]): sequence.append(pools[category][indexes[category]]); indexes[category] += 1; added = True
        if not added: break
    return sequence

_topic_pool_for_month = topic_pool_for_month
