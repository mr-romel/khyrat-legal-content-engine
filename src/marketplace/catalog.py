"""Initial Marketplace service catalog; independent from Core."""

from __future__ import annotations

SERVICE_CATALOG = [
    {"topic": "مراجعة العقود التجارية", "platform": "khamsat", "priority": 1},
    {"topic": "صياغة عقد عمل", "platform": "khamsat", "priority": 2},
    {"topic": "صياغة عقد شراكة", "platform": "khamsat", "priority": 3},
    {"topic": "مراجعة لائحة أو سياسة عمل", "platform": "khamsat", "priority": 4},
    {"topic": "مراجعة بنود واتفاقيات الشركات", "platform": "khamsat", "priority": 5},
    {"topic": "استشارة قانونية تجارية", "platform": "khamsat", "priority": 6},
]


def prioritized_topics() -> list[str]:
    return [x["topic"] for x in sorted(SERVICE_CATALOG, key=lambda x: x["priority"])]
