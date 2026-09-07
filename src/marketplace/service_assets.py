"""Publish-ready marketplace service assets, without platform publishing."""
from __future__ import annotations

from typing import Any


def build_khamsat_package(service: dict[str, Any]) -> dict[str, Any]:
    """Turn a service draft into a complete human-review package."""
    title = str(service.get("title", "")).strip()
    description = str(service.get("description", "")).strip()
    deliverables = [str(x).strip() for x in service.get("deliverables", []) if str(x).strip()]
    if not title or not description:
        raise ValueError("عنوان الخدمة ووصفها مطلوبان")
    return {
        "title": title,
        "description": description,
        "deliverables": deliverables,
        "requirements": [
            "إرسال نسخة واضحة من العقد أو المستند المطلوب مراجعته.",
            "توضيح الغرض من المستند وأي نقطة محددة تثير القلق.",
            "ذكر الدولة والقانون الواجب التطبيق إذا كان ذلك مهماً للمراجعة.",
        ],
        "faq": [
            {"q": "هل المراجعة تشمل تعديل العقد؟", "a": "نعم، بحسب نطاق الخدمة يتم تحديد البنود محل الخطر والتعديلات المقترحة."},
            {"q": "هل أحتاج إلى إرسال بيانات سرية؟", "a": "أرسل فقط ما يلزم لتنفيذ الخدمة، مع تجنب أي بيانات غير ضرورية."},
            {"q": "هل هذه الخدمة تغني عن التمثيل القانوني؟", "a": "الخدمة مخصصة للمراجعة أو الصياغة المحددة ولا تُعد توكيلاً أو تمثيلاً أمام الجهات."},
        ],
        "upgrades": [
            {"name": "تسليم عاجل", "description": "تقليل مدة التنفيذ وفقاً لإمكانية العمل."},
            {"name": "جلسة شرح", "description": "شرح الملاحظات والتعديلات المقترحة في مكالمة قصيرة."},
        ],
        "creative_assets": {
            "builder": "marketplace.creative_assets.build_service_assets",
            "cover_size": "1700x970",
            "portfolio_size": "800x460",
            "usage_note": "Brand/presentation asset only; not a client work sample.",
        },
        "review_status": "READY_FOR_REVIEW",
    }


def build_all_packages(services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [build_khamsat_package(service) for service in services]
