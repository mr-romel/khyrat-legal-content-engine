from __future__ import annotations

from src.topic_bank import CATEGORY_COUNTS as BASE_CATEGORY_COUNTS
from src.topic_bank import TOPIC_BANK as BASE_TOPIC_BANK


VARIANT_PROFILES = (
    {
        "label": "من منظور القرار الصحيح قبل التصرف",
        "angle": "قرار عملي قبل اتخاذ خطوة قد يصعب التراجع عنها",
        "format": "دليل قرار",
        "objective": "تحويل المشاهد من رد فعل سريع إلى قرار قانوني محسوب",
    },
    {
        "label": "من منظور المستند والدليل",
        "angle": "ما الذي يجب توثيقه أو الاحتفاظ به قبل النزاع؟",
        "format": "قائمة فحص",
        "objective": "زيادة قيمة التوثيق المبكر وحماية الموقف القانوني",
    },
    {
        "label": "من منظور التفاوض والوقاية",
        "angle": "كيف تمنع المشكلة أو تفاوض على حل أفضل قبل التصعيد؟",
        "format": "سيناريو تفاوضي",
        "objective": "إظهار قيمة الاستشارة القانونية المبكرة وتقليل تكلفة النزاع",
    },
)


# The original 200 briefs remain the curated base bank. We deliberately derive
# additional editorial briefs instead of duplicating titles verbatim. Each derived
# brief changes the angle, format and objective while preserving the legal subject
# and its source family. This makes the active bank 500 publishable briefs without
# deleting the proven 200-topic baseline.
TOPIC_BANK = [dict(item) for item in BASE_TOPIC_BANK]

for category in sorted(BASE_CATEGORY_COUNTS):
    category_items = [item for item in BASE_TOPIC_BANK if item["category"] == category]
    # 20 subjects receive two additional editorial variants; the remaining 20
    # receive one. Thus each of the five categories grows from 40 to exactly 100.
    for index, base in enumerate(category_items):
        variant_count = 2 if index < 20 else 1
        for variant_index in range(variant_count):
            profile = VARIANT_PROFILES[(index + variant_index) % len(VARIANT_PROFILES)]
            variant = dict(base)
            variant["topic"] = f"{base['topic']} — {profile['label']}"
            variant["angle"] = profile["angle"]
            variant["format"] = profile["format"]
            variant["objective"] = profile["objective"]
            TOPIC_BANK.append(variant)


CATEGORY_COUNTS = {
    category: sum(1 for item in TOPIC_BANK if item["category"] == category)
    for category in sorted({item["category"] for item in TOPIC_BANK})
}

if len(TOPIC_BANK) != 500:
    raise RuntimeError(f"TOPIC_BANK_500 must contain exactly 500 briefs; found {len(TOPIC_BANK)}")

EXPECTED_COUNTS = {
    "القانون الجنائي": 100,
    "قانون الأسرة": 100,
    "قانون العمل الجديد": 100,
    "قانون الشركات والاستثمار": 100,
    "القانون الإداري": 100,
}

if CATEGORY_COUNTS != EXPECTED_COUNTS:
    raise RuntimeError(f"Unexpected 500-topic category distribution: {CATEGORY_COUNTS}")

if len({item["topic"] for item in TOPIC_BANK}) != 500:
    raise RuntimeError("TOPIC_BANK_500 contains duplicate topic titles")

if not all(item["angle"].strip() and item["format"].strip() and item["objective"].strip() for item in TOPIC_BANK):
    raise RuntimeError("TOPIC_BANK_500 contains incomplete editorial metadata")
