from __future__ import annotations

import re
from collections import Counter


STYLES = (
    ("موقف يومي", "ابدأ بموقف واقعي قصير كأن المتابع يحكيه لمحامٍ، ثم اشرح أين تكمن المشكلة القانونية."),
    ("سؤال مباشر", "ابدأ بسؤال طبيعي من نوع الأسئلة التي تصل للمحامي، ثم جاوب تدريجيًا بدون مقدمة مدرسية."),
    ("خطأ شائع", "ابدأ بفكرة منتشرة لكنها قد تقود لتصرف خاطئ، ثم صححها ووضح التصرف الأكثر أمانًا."),
    ("قرار قبل التصرف", "ابدأ باللحظة التي يكون فيها الشخص على وشك اتخاذ قرار، ووضح ماذا يفحص قبل أن يتحرك."),
    ("حكاية قصيرة", "استخدم سيناريو مختصرًا من الحياة اليومية بأشخاص افتراضيين، ثم استخرج منه القاعدة العملية."),
    ("صح أم غلط", "اعرض اعتقادًا شائعًا بصيغة بسيطة، ثم بيّن الجزء الصحيح والجزء الذي يحتاج تصحيحًا."),
    ("من واقع الشغل", "قدّم الموضوع كما يشرحه محامٍ لعميل أو صاحب عمل في حديث عملي، بلا لغة مذكرات أو كتب دراسية."),
    ("ماذا تفعل؟", "اجعل المنشور مسار قرار عمليًا: لو حصل كذا، افحص كذا، وخد بالك من كذا."),
)

FORBIDDEN_OPENERS = (
    "في هذا المقال", "في عالمنا اليوم", "دعونا نتعرف", "من الجدير بالذكر",
    "لا شك أن", "يُعد هذا الموضوع من", "يعتبر هذا الموضوع من",
)

FORBIDDEN_AI_MARKERS = (
    "بدايةً", "ختامًا", "وفي الختام", "أود أن أوضح", "سوف نستعرض",
    "سنستعرض", "لنستعرض", "من المهم جدًا أن نعلم",
)


def _recent_angles(previous_context: str) -> list[str]:
    angles: list[str] = []
    for line in (previous_context or "").splitlines():
        match = re.search(r"\|\s*الزاوية:\s*(.*?)\s*\|", line)
        if match:
            angle = match.group(1).strip()
            if angle:
                angles.append(angle)
    return angles[-12:]


def _recent_openings(previous_context: str) -> list[str]:
    openings: list[str] = []
    for line in (previous_context or "").splitlines():
        match = re.search(r"\|\s*النص السابق:\s*(.*)$", line)
        if not match:
            continue
        text = match.group(1).strip()
        if text:
            openings.append(" ".join(text.split()[:12]))
    return openings[-8:]


def choose_style(topic: str, previous_context: str = "") -> tuple[str, str]:
    recent = _recent_angles(previous_context)
    counts = Counter(recent)
    seed = sum(ord(ch) for ch in (topic or ""))
    ranked = sorted(
        STYLES,
        key=lambda item: (counts.get(item[0], 0), (seed + len(item[0]) * 17) % len(STYLES)),
    )
    return ranked[0]


def build_diversity_context(topic: str, previous_context: str = "") -> str:
    style_name, instruction = choose_style(topic, previous_context)
    recent = _recent_angles(previous_context)
    openings = _recent_openings(previous_context)
    recent_text = "، ".join(recent[-6:]) if recent else "لا يوجد سجل كافٍ"
    openings_text = " | ".join(openings[-5:]) if openings else "لا يوجد سجل كافٍ"
    return f"""
EDITORIAL DIVERSITY CONTROL
الأسلوب المختار لهذا المنشور: {style_name}
التوجيه: {instruction}

الزوايا الأخيرة: {recent_text}
افتتاحيات/بدايات حديثة يجب عدم تقليدها: {openings_text}

قواعد التنويع:
- لا تكرر افتتاحية أو أول جملة من منشور حديث.
- لا تعيد نفس تركيب الجمل أو نفس ترتيب الأفكار لمجرد أن الموضوع مختلف.
- لا تجعل كل منشور قائمة مرقمة أو عناوين فرعية.
- نوّع بين سؤال، موقف، حكاية، تصحيح اعتقاد، ومسار قرار حسب الأسلوب المختار.
- اكتب كأن محاميًا مصريًا يشرح لواحد من الناس، مع الحفاظ على المهنية والدقة.
- استخدم لغة مصرية طبيعية عند الحاجة، بدون مبالغة أو عامية مصطنعة.
- تجنب أي عبارة توحي بأن النص مولد آليًا.
- لا تذكر "الذكاء الاصطناعي" أو "AI" أو طريقة إنتاج المحتوى.
- لا تستخدم أيًا من الافتتاحيات أو العبارات النمطية التالية: {" | ".join(FORBIDDEN_OPENERS + FORBIDDEN_AI_MARKERS)}
- اجعل الـCTA خفيفة وطبيعية، وليست دعوة مباشرة للبيع.
""".strip()
