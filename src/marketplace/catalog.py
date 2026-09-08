"""Initial Marketplace service catalog; independent from Core."""

from __future__ import annotations

SERVICE_CATALOG = [
    {"topic": "مراجعة العقود التجارية", "platform": "khamsat", "priority": 1},
    {"topic": "صياغة عقد عمل", "platform": "khamsat", "priority": 2},
    {"topic": "مراجعة عقد عمل", "platform": "khamsat", "priority": 3},
    {"topic": "صياغة عقد شراكة", "platform": "khamsat", "priority": 4},
    {"topic": "صياغة ومراجعة اتفاقيات الشركات", "platform": "khamsat", "priority": 5},
    {"topic": "مراجعة لائحة أو سياسة عمل", "platform": "khamsat", "priority": 6},
    {"topic": "صياغة اتفاقية سرية معلومات NDA", "platform": "khamsat", "priority": 7},
    {"topic": "مراجعة شروط وأحكام المواقع والمتاجر", "platform": "khamsat", "priority": 8},
    {"topic": "مراجعة سياسة الخصوصية قانونيًا", "platform": "khamsat", "priority": 9},
    {"topic": "مراجعة بنود واتفاقيات الشركات", "platform": "khamsat", "priority": 10},
    {"topic": "صياغة إنذار ومطالبة قانونية", "platform": "khamsat", "priority": 11},
    {"topic": "استشارة قانونية تجارية متخصصة", "platform": "khamsat", "priority": 12},
]


def prioritized_topics() -> list[str]:
    return [x["topic"] for x in sorted(SERVICE_CATALOG, key=lambda x: x["priority"])]
