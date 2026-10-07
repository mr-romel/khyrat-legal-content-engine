from __future__ import annotations

import re
import requests

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


GOOGLE_SUGGEST_URL = "https://suggestqueries.google.com/complete/search"


def _google_suggest(query: str) -> list[str]:
    try:
        response = requests.get(
            GOOGLE_SUGGEST_URL,
            params={"client": "firefox", "q": query, "hl": "ar", "gl": "eg"},
            headers={"User-Agent": "Mozilla/5.0 Khyrat-Legal-Content-Engine/1.0"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        suggestions = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        return [str(x).strip() for x in suggestions if str(x).strip()]
    except Exception as exc:
        print(f"Google Suggest hashtags unavailable for {query!r}: {exc}")
        return []


def _hashtag_from_phrase(phrase: str) -> str:
    words = re.findall(r"[\u0600-\u06FFA-Za-z0-9]+", str(phrase or ""))
    words = [w for w in words if len(w) >= 2]
    if not words:
        return ""
    return "#" + "_".join(words[:5])


def build_hashtags(topic: str, *, max_tags: int = 8) -> list[str]:
    text = str(topic or "").strip().casefold()
    tags: list[str] = []
    seen: set[str] = set()

    # Use Google autocomplete as a search-language signal, not as a ranking trick.
    # This captures the phrases people actually type around the topic in Egypt.
    queries = [text, f"{text} قانون", f"{text} مصر", f"ماذا أفعل إذا {text}"]
    suggestions: list[str] = []
    for query in queries:
        suggestions.extend(_google_suggest(query))

    for suggestion in suggestions:
        tag = _hashtag_from_phrase(suggestion)
        if not tag or tag.casefold() in seen:
            continue
        # Keep tags tightly related to the actual topic and avoid sentence-like tags.
        words = set(re.findall(r"[\u0600-\u06FFA-Za-z0-9]+", suggestion.casefold()))
        topic_words = set(re.findall(r"[\u0600-\u06FFA-Za-z0-9]+", text))
        if topic_words and not (words & topic_words) and not any(k in suggestion for k in ("قانون", "حقوق", "محكمة", "دعوى", "عقد", "شركة", "عمل", "إيجار")):
            continue
        seen.add(tag.casefold())
        tags.append(tag)
        if len(tags) >= max_tags - len(CORE_HASHTAGS):
            break

    # Stable legal brand/category tags are added after the search-derived terms.
    for tag in CORE_HASHTAGS:
        if tag.casefold() not in seen and len(tags) < max_tags:
            seen.add(tag.casefold())
            tags.append(tag)

    # Deterministic keyword fallback when Google Suggest is unavailable.
    if len(tags) < min(max_tags, 6):
        for keyword, tag in KEYWORD_HASHTAGS.items():
            if keyword.casefold() in text and tag.casefold() not in seen and len(tags) < max_tags:
                seen.add(tag.casefold())
                tags.append(tag)

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
