from __future__ import annotations

import re

CORE_HASHTAGS = ["#قانون", "#محامي", "#استشارات_قانونية", "#قانون_مصري"]

KEYWORD_HASHTAGS = {
    "عقد": "#عقود",
    "عقود": "#عقود",
    "شركة": "#شركات",
    "قرار": "#إدارة_المخاطر",
    "مسؤولية": "#إدارة_المخاطر",
    "تعاقد": "#عقود",
    "شركات": "#شركات",
    "عمل": "#قانون_العمل",
    "عمال": "#قانون_العمل",
    "موظف": "#قانون_العمل",
    "موظفين": "#قانون_العمل",
    "إيجار": "#الإيجار",
    "ايجار": "#الإيجار",
    "مستأجر": "#الإيجار",
    "مالك": "#الإيجار",
    "تجاري": "#قانون_تجاري",
    "تجارة": "#قانون_تجاري",
    "شيك": "#شيكات",
    "شيكات": "#شيكات",
    "ميراث": "#مواريث",
    "تركة": "#مواريث",
    "طلاق": "#أحوال_شخصية",
    "زواج": "#أحوال_شخصية",
    "نفقة": "#أحوال_شخصية",
    "أسرة": "#أحوال_شخصية",
    "اسرة": "#أحوال_شخصية",
    "جنائي": "#قانون_جنائي",
    "جريمة": "#قانون_جنائي",
    "جناي": "#قانون_جنائي",
    "مدني": "#قانون_مدني",
    "تعويض": "#تعويضات",
    "دعوى": "#دعاوى",
    "محكمة": "#محاكم",
    "حكم": "#أحكام_قضائية",
    "استثمار": "#استثمار",
    "ضريبة": "#ضرائب",
    "ضرائب": "#ضرائب",
    "تأمين": "#تأمين",
    "علامة": "#ملكية_فكرية",
    "براءة": "#ملكية_فكرية",
    "ملكية": "#ملكية_فكرية",
}

AI_SIGNAL_PATTERNS = (
    "ذكاء اصطناعي",
    "الذكاء الاصطناعي",
    "مولد آلي",
    "مولد تلقائي",
    "محتوى مولد",
    "نموذج لغوي",
    "بواسطة النموذج",
    "تم توليد",
)

QUOTE_CHARS = str.maketrans({
    "«": "", "»": "", "“": "", "”": "", "„": "", "‟": "", '"': "", "′": "", "″": "",
})

def sanitize_social_copy(post: str) -> str:
    """Normalize human-style social copy without changing its substantive meaning."""
    text = str(post or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(QUOTE_CHARS)
    for marker in AI_SIGNAL_PATTERNS:
        text = re.sub(re.escape(marker), "", text, flags=re.IGNORECASE)
    # Remove sentence-final full stops while preserving question/exclamation punctuation,
    # decimals, URLs, and hashtag syntax.
    text = re.sub(r"[.。]+(?=\s+(?:[A-Za-z\u0600-\u06FF])|\s*$)", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

HASHTAG_RE = re.compile(
    r"(?<!\w)#(?:[\w\u0600-\u06FF]+(?:_[\w\u0600-\u06FF]+)*)",
    re.UNICODE,
)


def build_hashtags(topic: str, *, max_tags: int = 8) -> list[str]:
    text = str(topic or "").strip().casefold()
    tags: list[str] = list(CORE_HASHTAGS)
    for keyword, tag in KEYWORD_HASHTAGS.items():
        if keyword.casefold() in text and tag not in tags:
            tags.append(tag)
        if len(tags) >= max_tags:
            break
    return tags[:max_tags]


def append_hashtags(post: str, topic: str, *, max_tags: int = 8) -> str:
    text = sanitize_social_copy(str(post or "").strip())
    if not text:
        return text
    existing = set(HASHTAG_RE.findall(text))
    tags = [tag for tag in build_hashtags(topic, max_tags=max_tags) if tag not in existing]
    if not tags:
        return text
    return sanitize_social_copy(f"{text.rstrip()}\n\n{' '.join(tags)}")


def split_hashtags(post: str) -> tuple[str, str]:
    text = str(post or "").strip()
    if not text:
        return "", ""
    matches = list(HASHTAG_RE.finditer(text))
    if not matches:
        return text, ""
    start = matches[0].start()
    return text[:start].rstrip(), text[start:].strip()
