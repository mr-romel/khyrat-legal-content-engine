from __future__ import annotations


def classify(topic: str, post: str = "") -> tuple[str, str]:
    """Classify content against the firm's confirmed service portfolio."""
    text = f"{topic} {post}".casefold()

    # Specific legal domains come first to avoid broad words such as عقد or عمل
    # swallowing criminal, family, or commercial topics.
    if any(word in text for word in ("جنائي", "جريمة", "حبس", "بلاغ", "محضر", "اتهام", "دفاع جنائي")):
        pillar = "القضايا الجنائية"
    elif any(word in text for word in ("طلاق", "نفقة", "حضانة", "زواج", "أسرة", "أحوال شخصية", "رؤية", "تمكين")):
        pillar = "قضايا الأسرة والأحوال الشخصية"
    elif any(word in text for word in ("عامل", "موظف", "فصل", "مرتب", "راتب", "أجر", "إجازة", "جزاء", "استقالة", "قانون العمل")):
        pillar = "القضايا العمالية"
    elif any(word in text for word in ("منازعة تجارية", "نزاع تجاري", "تاجر", "توريد", "وكالة تجارية", "توزيع", "معاملات تجارية")):
        pillar = "منازعات الشركات والتجارة"
    elif any(word in text for word in ("تأسيس شركة", "تأسيس الشركات", "شريك", "حصة", "جمعية عامة", "مجلس إدارة", "مدير شركة", "حوكمة")):
        pillar = "تأسيس الشركات ومنازعات الشركات"
    elif any(word in text for word in ("عقد", "اتفاق", "بند", "شرط", "تعاقد", "صياغة", "مراجعة عقد")):
        pillar = "تأسيس الشركات وصياغة العقود"
    elif any(word in text for word in ("تعويض", "مسؤولية مدنية", "مدني", "دين", "مديونية", "شيك", "إيصال أمانة", "مطالبة مالية", "إيجار")):
        pillar = "القضايا المدنية والتعويضات"
    elif any(word in text for word in ("استشارة", "استفسار قانوني", "رأي قانوني", "مراجعة مستندات")):
        pillar = "الاستشارات القانونية"
    else:
        pillar = "التوعية القانونية والخدمات القانونية العامة"

    if any(word in text for word in ("كيف", "ماذا أفعل", "ماذا افعل", "أعمل إيه", "اعمل ايه", "خطوات", "إجراءات")):
        objective = "ENGAGEMENT"
    elif any(word in text for word in ("استشارة", "محامي", "حجز", "تأسيس شركة", "صياغة عقد", "مراجعة عقد")):
        objective = "LEAD_GENERATION"
    elif any(word in text for word in ("حكم", "مبدأ", "قانون", "مادة", "نقض")):
        objective = "AUTHORITY"
    else:
        objective = "REACH"
    return pillar, objective
