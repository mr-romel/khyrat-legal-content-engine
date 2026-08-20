from __future__ import annotations


def classify(topic: str, post: str = "") -> tuple[str, str]:
    text = f"{topic} {post}".casefold()
    if any(word in text for word in ["شركة", "عقد", "موظف", "عامل", "فصل", "راتب", "عمل"]):
        pillar = "الشركات والعمل"
    elif any(word in text for word in ["جريمة", "جنائي", "حبس", "بلاغ", "محضر"]):
        pillar = "المشاكل القانونية اليومية"
    elif any(word in text for word in ["ميراث", "وصية", "زواج", "طلاق", "أسرة"]):
        pillar = "الأسرة والميراث"
    elif any(word in text for word in ["حكم", "محكمة", "نقض", "مبدأ"]):
        pillar = "الأحكام والمبادئ القضائية"
    else:
        pillar = "التوعية القانونية اليومية"

    if any(word in text for word in ["كيف", "ماذا تفعل", "تعمل ايه", "تعمل إيه", "خطوات"]):
        objective = "ENGAGEMENT"
    elif any(word in text for word in ["شركة", "عقد", "استشارة", "محامي"]):
        objective = "LEAD_GENERATION"
    elif any(word in text for word in ["حكم", "مبدأ", "قانون"]):
        objective = "AUTHORITY"
    else:
        objective = "REACH"
    return pillar, objective
