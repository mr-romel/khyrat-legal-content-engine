from __future__ import annotations

import hashlib
from calendar import monthrange

from sheets import row_to_dict
from topic_bank_500 import TOPIC_BANK
from topic_bank_expanded import EXTRA_TOPICS
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
ANGLE_FORMATS = {
    "خطأ شائع يقع فيه الناس وكيف يتجنبونه": ("خطأ شائع", "صح أم خطأ", "تصحيح خطأ عملي شائع"),
    "موقف واقعي قصير وما التصرف القانوني الصحيح": ("حالة واقعية", "سيناريو عملي", "ربط القانون بموقف يومي"),
    "متى يكون الحق ثابتًا ومتى قد يضيع؟": ("حدود الحق", "دليل قرار", "توضيح متى يحمي القانون صاحب الحق"),
    "أهم مستند أو دليل يحمي صاحب الحق": ("المستند والدليل", "قائمة فحص", "رفع جودة التوثيق"),
    "ماذا تفعل خلال أول 24 ساعة من المشكلة؟": ("أول 24 ساعة", "خريطة طريق", "تحديد الخطوة الأولى"),
    "الفرق بين التصور الشائع والحقيقة القانونية": ("تصحيح مفهوم", "سؤال وجواب", "تصحيح معلومة منتشرة"),
    "3 علامات تحذيرية قبل اتخاذ القرار": ("إنذار مبكر", "3 علامات", "كشف المخاطر"),
    "متى تحتاج لمحامٍ ومتى يمكن اتخاذ خطوة أولية بنفسك؟": ("متى تحتاج لمحامٍ", "دليل قرار", "تحديد مستوى المساعدة القانونية"),
    "أكثر سؤال يتكرر حول الموضوع وإجابته العملية": ("سؤال متكرر", "سؤال وجواب", "إجابة مباشرة"),
    "كيف تنظر المحكمة عادةً للمشكلة بصورة مبسطة؟": ("عين المحكمة", "تبسيط قضائي", "تقريب طريقة تقييم النزاع"),
    "خطوة تبدو صحيحة لكنها قد تضر بموقفك": ("خطوة خطرة", "تحذير", "منع خطأ مكلف"),
    "مقارنة بين تصرفين ونتيجة كل منهما": ("قارن قبل ما تتصرف", "مقارنة", "إظهار الفرق بين مسارين"),
    "سيناريو عائلي أو عملي شائع مرتبط بالموضوع": ("من الحياة", "قصة قصيرة", "تقديم القانون في قصة مفهومة"),
    "ما الذي يجب ألا توقع عليه أو تتنازل عنه؟": ("قبل التوقيع", "قائمة فحص", "حماية الحقوق قبل التنازل"),
    "Checklist عملية قبل بدء أي إجراء": ("قبل الإجراء", "Checklist", "تقليل الأخطاء الإجرائية"),
    "زاوية جديدة تركز على الوقاية قبل وقوع المشكلة": ("الوقاية", "3 خطوات", "حل المشكلة قبل وقوعها"),
}


def _expanded_bank() -> list[dict[str, str]]:
    sources = {
        "القانون الجنائي": "قانون العقوبات المصري وقانون الإجراءات الجنائية والنصوص الخاصة ذات الصلة؛ تحقق من النص النافذ قبل النشر.",
        "قانون الشركات والاستثمار": "قانون الشركات المصري وقوانين الاستثمار واللوائح والقرارات المنظمة؛ تحقق من نوع الشركة والنص النافذ قبل النشر.",
        "قانون الأسرة": "قوانين الأحوال الشخصية المصرية والنصوص واللوائح والأحكام المنظمة؛ تحقق من القانون النافذ والوقائع قبل النشر.",
        "قانون العمل الجديد": "قانون العمل المصري الجديد واللوائح والقرارات التنفيذية ذات الصلة؛ تحقق من النص النافذ وتاريخ سريانه قبل النشر.",
        "القانون الإداري": "قوانين مجلس الدولة والوظيفة العامة والقرارات الإدارية المنظمة؛ تحقق من النص النافذ والاختصاص قبل النشر.",
    }
    sizes = (20, 20, 20, 20, 18)
    result: list[dict[str, str]] = []
    offset = 0
    for category, size in zip(CATEGORY_ORDER, sizes):
        for subject in EXTRA_TOPICS[offset:offset + size]:
            for angle in ANGLE_LIBRARY:
                fmt, label, objective = ANGLE_FORMATS[angle]
                result.append({"topic": subject, "category": category, "angle": angle, "format": label, "objective": objective, "legal_sources": sources[category]})
        offset += size
    return result


EXPANDED_TOPIC_BANK = TOPIC_BANK + _expanded_bank()
if len(EXPANDED_TOPIC_BANK) != 2068:
    raise RuntimeError(f"Expanded bank invariant failed: expected 2068 briefs, found {len(EXPANDED_TOPIC_BANK)}")
if len(set(EXTRA_TOPICS)) != len(EXTRA_TOPICS):
    raise RuntimeError("Expanded subject catalog contains duplicate subjects")


def month_key(value: str) -> str:
    try: return parse_date(value).strftime("%Y-%m")
    except Exception: return ""


def posting_days(year: int, month: int, start_day: int) -> list[int]:
    return list(range(start_day, monthrange(year, month)[1] + 1))


def normalize_topic(value: str) -> str:
    text = " ".join((value or "").split()).strip()
    if " — زاوية جديدة:" in text: text = text.split(" — زاوية جديدة:", 1)[0].strip()
    return text.casefold()


def brief_key(item: dict[str, str]) -> tuple[str, str, str]:
    return (str(item.get("category", "")).strip().casefold(), normalize_topic(item.get("topic", "")), str(item.get("angle", "")).strip().casefold())


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


def historically_used_base_topics(values: list[list[str]], current_key: str) -> set[str]:
    used = set(); marker = f"{RECYCLE_MARKER}:{current_key}"
    for raw in values[1:]:
        row = row_to_dict(raw); topic = row.get("الموضوع", "").strip(); notes = row.get("ملاحظات", "")
        if is_published(row) or marker in notes:
            if topic: used.add(base_topic_key(topic))
            if "الموضوع الأصلي:" in notes:
                original = notes.split("الموضوع الأصلي:", 1)[1].split("|", 1)[0].strip()
                if original: used.add(base_topic_key(original))
    return used


def historically_used_categories(values: list[list[str]], current_key: str) -> dict[str, int]:
    counts = {category: 0 for category in CATEGORY_ORDER}; marker = f"{RECYCLE_MARKER}:{current_key}"
    for raw in values[1:]:
        row = row_to_dict(raw); notes = row.get("ملاحظات", "")
        if not (is_published(row) or marker in notes): continue
        category = notes.split("القسم:", 1)[1].split("|", 1)[0].strip() if "القسم:" in notes else ""
        if category in counts: counts[category] += 1
    return counts


def historically_used_angles(values: list[list[str]], current_key: str) -> dict[str, int]:
    counts: dict[str, int] = {angle: 0 for angle in ANGLE_LIBRARY}; marker = f"{RECYCLE_MARKER}:{current_key}"
    for raw in values[1:]:
        row = row_to_dict(raw); notes = row.get("ملاحظات", "")
        if not (is_published(row) or marker in notes): continue
        angle = notes.split("زاوية:", 1)[1].split("|", 1)[0].strip() if "زاوية:" in notes else ""
        if angle: counts[angle] = counts.get(angle, 0) + 1
    return counts


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


def brief_notes(current_key: str, brief: dict[str, str], posting_time: str, source: str = "Expanded-Topic-Bank") -> str:
    return f"{RECYCLE_MARKER}:{current_key} | الموضوع الأصلي: {brief['topic'].strip()} | القسم: {brief['category']} | زاوية: {brief['angle'].strip()} | الصيغة: {brief['format'].strip()} | الهدف: {brief['objective'].strip()} | Slot: {posting_time} | المصدر: {source} | لا يعاد استخدام الموضوع أو نفس الفكرة الأساسية قبل استنفاد بنك الموضوعات | ساعة النشر مثبتة تلقائيًا"


def legacy_source_for_slot(source_rows_list: list[dict[str, str]], index: int, used_topics: set[str]) -> dict[str, str] | None:
    if not source_rows_list: return None
    for offset in range(len(source_rows_list)):
        candidate = source_rows_list[(index + offset) % len(source_rows_list)]
        if normalize_topic(candidate.get("الموضوع", "")) not in used_topics: return candidate
    return None


def base_topic_key(value: str) -> str:
    text = normalize_topic(value)
    parts = [part.strip() for part in text.split(" — ") if part.strip()]
    return parts[0] if parts else text


def topic_pool_for_month(current_key: str, used_topics: set[str]) -> list[dict[str, str]]:
    used = {str(value).strip().casefold() for value in (used_topics or set()) if str(value).strip()}
    available = [item for item in EXPANDED_TOPIC_BANK if normalize_topic(item["topic"]) not in used]
    if not available: available = list(EXPANDED_TOPIC_BANK)
    def rank(item): return hashlib.sha256(f"{current_key}|{item['category']}|{item['topic']}|{item['angle']}".encode("utf-8")).hexdigest()
    buckets = {category: [] for category in CATEGORY_ORDER}; extras = []
    for item in available: (buckets[item["category"]] if item["category"] in buckets else extras).append(item)
    for bucket in buckets.values(): bucket.sort(key=rank)
    extras.sort(key=rank)
    start = int(hashlib.sha256(current_key.encode("utf-8")).hexdigest()[:8], 16) % len(CATEGORY_ORDER)
    ordered_categories = [CATEGORY_ORDER[(start + i) % len(CATEGORY_ORDER)] for i in range(len(CATEGORY_ORDER))]
    result = []
    while any(buckets[c] for c in ordered_categories):
        for category in ordered_categories:
            if buckets[category]: result.append(buckets[category].pop(0))
    result.extend(extras)
    if len(result) != len(available) or len({brief_key(item) for item in result}) != len(available):
        raise RuntimeError("Topic rotation invariant failed: briefs were lost or duplicated")
    return result


def adaptive_topic_pool(current_key, used_topics, category_counts=None, angle_counts=None):
    pool = topic_pool_for_month(current_key, used_topics)
    category_counts = category_counts or {}; angle_counts = angle_counts or {}
    counts = {category: int(category_counts.get(category, 0)) for category in CATEGORY_ORDER}
    return sorted(pool, key=lambda item: (counts.get(item.get("category", ""), 0), int(angle_counts.get(item.get("angle", ""), 0)), hashlib.sha256(f"{current_key}|{item['topic']}|{item['angle']}".encode("utf-8")).hexdigest()))

_topic_pool_for_month = topic_pool_for_month
