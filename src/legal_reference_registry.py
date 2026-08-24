from __future__ import annotations

from datetime import datetime, timezone


# Source hierarchy used by Gemini during legal research.
# Tier 1 = primary/official sources; Tier 2 = specialist legal sources;
# Tier 3 = explanatory material. Lower tiers may help discover leads but
# must never be the sole basis for a material legal conclusion.
SOURCE_REGISTRY = (
    {
        "tier": 1,
        "name": "محكمة النقض المصرية / مجلس القضاء الأعلى",
        "domains": ["cc.gov.eg", "register.cc.gov.eg"],
        "uses": "التشريعات المنشورة، مبادئ وأحكام النقض، النشرات التشريعية والقانونية، ومتابعة المستحدث.",
    },
    {
        "tier": 1,
        "name": "المحكمة الدستورية العليا المصرية",
        "domains": ["sccourt.gov.eg"],
        "uses": "أحكام الدستورية، التفسير، المنازعات الدستورية ومبادئ الحجية والنطاق الدستوري.",
    },
    {
        "tier": 1,
        "name": "وزارة العدل والجهات القضائية/الحكومية المصرية المختصة",
        "domains": [
            "moj.gov.eg",
            "cabinet.gov.eg",
            "presidency.eg",
            "ppo.gov.eg",
        ],
        "uses": "القرارات والإعلانات والمعلومات التنظيمية الرسمية بحسب الاختصاص.",
    },
    {
        "tier": 1,
        "name": "الجهة التنظيمية أو الحكومية المختصة بالموضوع",
        "domains": [
            "gafi.gov.eg",
            "fra.gov.eg",
            "cbe.org.eg",
            "mof.gov.eg",
            "eta.gov.eg",
            "nosi.gov.eg",
            "mohp.gov.eg",
            "moi.gov.eg",
        ],
        "uses": "التنظيمات والقرارات والتعليمات الرسمية في نطاق الاختصاص فقط.",
    },
    {
        "tier": 2,
        "name": "منشورات قانونية",
        "domains": ["manshurat.org"],
        "uses": "الوصول إلى نصوص وتشريعات وأحكام منشورة ومقارنة النتائج، مع عدم اعتباره بديلًا عن المصدر الرسمي عند توفره.",
    },
    {
        "tier": 3,
        "name": "مصادر أكاديمية ومهنية متخصصة",
        "domains": [],
        "uses": "الشرح والسياق واكتشاف المسائل الخلافية فقط؛ لا تكفي وحدها لإثبات ادعاء قانوني جوهري.",
    },
)


def _registry_lines() -> list[str]:
    lines: list[str] = []
    for source in SOURCE_REGISTRY:
        domains = ", ".join(source["domains"]) if source["domains"] else "لا توجد قائمة نطاقات ثابتة"
        lines.append(
            f"Tier {source['tier']} | {source['name']} | domains: {domains} | use: {source['uses']}"
        )
    return lines


def build_reference_context(*, user_sources: str = "") -> str:
    now = datetime.now(timezone.utc).astimezone()
    lines = [
        "LEGAL SOURCE HIERARCHY — EGYPT ONLY",
        f"Research timestamp: {now.isoformat()}",
        "",
        "أولوية المصادر إلزامية: Tier 1 ثم Tier 2 ثم Tier 3.",
        "لا تجعل مصدرًا من Tier 2 أو Tier 3 هو الأساس الوحيد لنتيجة قانونية جوهرية إذا كان المصدر الأولي متاحًا.",
        "إذا وجدت تعارضًا بين مصدرين، لا تخترع حلًا؛ ابحث عن النص الأحدث/الأخص والمصدر القضائي أو الرسمي الحاسم، وإلا BLOCK/REVIEW.",
        "لا تعتبر نتيجة محرك البحث نفسها مصدرًا؛ المصدر هو الصفحة أو الوثيقة التي تقف وراء النتيجة.",
        "تحقق من تاريخ السريان والتعديلات والإلغاء والاستثناءات قبل اعتماد أي قاعدة.",
        "",
        *(_registry_lines()),
    ]
    if user_sources.strip():
        lines.extend(
            [
                "",
                "USER-PROVIDED SOURCES — treat as leads and verify independently:",
                user_sources.strip(),
            ]
        )
    return "\n".join(lines)


def extract_grounding_sources(response) -> list[dict[str, str]]:
    """Extract web grounding citations from Gemini without assuming one SDK shape."""
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    candidates = []
    for candidate in getattr(response, "candidates", []) or []:
        metadata = getattr(candidate, "grounding_metadata", None)
        if metadata is not None:
            candidates.append(metadata)
    for metadata in candidates:
        chunks = getattr(metadata, "grounding_chunks", None) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web is None:
                continue
            uri = str(getattr(web, "uri", "") or "").strip()
            title = str(getattr(web, "title", "") or "").strip()
            if not uri or uri in seen:
                continue
            seen.add(uri)
            result.append({"title": title, "url": uri})
    return result


def format_grounding_sources(sources: list[dict[str, str]]) -> str:
    if not sources:
        return "لم تُستخرج روابط Grounding من استجابة البحث."
    return "\n".join(
        f"{index}. {item.get('title', '')} — {item.get('url', '')}".strip()
        for index, item in enumerate(sources, start=1)
    )
