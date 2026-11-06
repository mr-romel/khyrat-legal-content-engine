from __future__ import annotations

import re
from urllib.parse import urlparse

from social_content import sanitize_topic

BLOGGER_HOST = "askmahmoudkhyrat.blogspot.com"
WHATSAPP_URL = "https://wa.me/201022718375"

# Distinct legal subject families. A Reel description must not mix two unrelated
# topics merely because the source Sheet cell accidentally contains both.
SUBJECT_FAMILIES = {
    "secret_threat": ("تهديد", "إفشاء", "افشاء", "أسرار", "اسرار", "ابتزاز", "مساومة"),
    "unauthorized_recording": ("تصوير", "التصوير", "كاميرا", "تسجيل", "التسجيل", "خصوصية الصورة"),
    "employment": ("عمل", "عامل", "عمال", "موظف", "موظفين", "أجر", "فصل", "استقالة"),
    "family": ("طلاق", "نفقة", "حضانة", "رؤية", "زواج", "أسرة", "اسرة", "ميراث"),
    "companies": ("شركة", "شركات", "شريك", "شراكة", "تأسيس", "تجاري"),
    "contracts": ("عقد", "عقود", "تعاقد", "فسخ", "إخلال"),
    "criminal": ("جريمة", "جنائي", "سرقة", "ضرب", "قتل", "سب", "قذف"),
}


def _clean(value: str, limit: int = 700) -> str:
    text = re.sub(r"https?://\\S+", "", str(value or ""))
    text = re.sub(r"\\s+", " ", text).strip()
    return text[:limit].rstrip(" ،؛:.")


def _public_topic(value: str) -> str:
    """Convert internal Sheet labels into a clean, audience-facing legal subject."""
    text = sanitize_topic(str(value or ""))
    text = re.sub(r"(?i)^\\s*(?:سؤال\\s+عن|استفسار\\s+عن|موضوع)\\s+", "", text)
    text = re.sub(
        r"(?i)\\s*(?:[—–|:؛-]\\s*)?(?:زاوية\\s*(?:جديدة|أخرى|اخري|اخرى|مختلفة)|"
        r"check\\s*[-_ ]?\\s*list|checklist|content\\s*angle|editorial\\s*angle).*$",
        "",
        text,
    )
    text = re.sub(r"\\s{2,}", " ", text).strip(" —–-:|،")
    return _clean(text, 180) or "معلومة قانونية"


def _valid_article_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname == BLOGGER_HOST and parsed.path not in {"", "/"}


def _topic_family(topic: str) -> str:
    normalized = str(topic or "").casefold()
    # More specific families must win over broad families.
    for family in ("secret_threat", "unauthorized_recording", "employment", "family", "companies", "contracts", "criminal"):
        if any(term in normalized for term in SUBJECT_FAMILIES[family]):
            return family
    return ""


def _topic_aligned_body(text: str, topic: str, limit: int = 900) -> str:
    """Keep narration sentences aligned to the Reel's actual legal subject."""
    raw = re.sub(r"https?://\\S+", "", str(text or ""))
    sentences = [part.strip() for part in re.split(r"(?<=[؟.!])\\s+|\\n+", raw) if part.strip()]
    family = _topic_family(topic)
    unrelated_families = [name for name in SUBJECT_FAMILIES if name != family]
    kept: list[str] = []
    for sentence in sentences:
        lower = sentence.casefold()
        if family and any(
            any(term in lower for term in SUBJECT_FAMILIES[other])
            for other in unrelated_families
        ):
            # A sentence that introduces a second legal subject is not copied into
            # this Reel's public metadata, even if it appeared in the same Sheet cell.
            continue
        sentence = re.sub(r"(?i)^🎬\\s*", "", sentence).strip()
        if sentence and sentence not in kept:
            kept.append(sentence)
    body = " ".join(kept)
    body = re.sub(r"\\s{2,}", " ", body).strip()
    if len(body) > limit:
        body = body[:limit].rsplit(" ", 1)[0].rstrip(" ،؛:") + "…"
    return body


def build_video_description(*, topic: str, post: str, script: str, article_url: str = "", platform: str = "facebook") -> str:
    """Build platform metadata from a clean topic and matching narration, never raw Sheet labels."""
    clean_topic = _public_topic(topic)
    platform = str(platform or "").strip().lower()
    if platform not in {"facebook", "youtube"}:
        raise ValueError("platform must be facebook or youtube")

    # The narration is the approved source of truth for this specific Reel.
    # Raw post text is only a fallback, and both paths pass the same topic filter.
    body = _topic_aligned_body(script, clean_topic) or _topic_aligned_body(post, clean_topic)
    if not body:
        raise ValueError("Cannot publish a video description without approved topic content.")

    lines = [
        f"🎬 {clean_topic}",
        "",
        body,
    ]
    if _valid_article_url(article_url):
        lines += ["", "📖 اقرأ المقال الكامل المرتبط بنفس الموضوع:", str(article_url).strip()]
    lines += [
        "",
        f"للاستفسارات القانونية: {WHATSAPP_URL}",
        "المحتوى للتوعية القانونية العامة، والتقييم النهائي بيتوقف على تفاصيل كل حالة ومستنداتها.",
    ]
    if platform == "youtube":
        tags = ["#معلومة_قانونية", "#اسأل_محمود"]
        topic_lower = clean_topic.lower()
        if any(word in topic_lower for word in ("عمل", "عامل", "عمال", "موظف")):
            tags.append("#حقوق_العمال")
        elif any(word in topic_lower for word in ("شركة", "شركات", "تجاري", "شراكة")):
            tags.append("#قانون_الشركات")
        elif any(word in topic_lower for word in ("أسرة", "طلاق", "نفقة", "حضانة")):
            tags.append("#الأحوال_الشخصية")
        elif any(word in topic_lower for word in ("جنائي", "جريمة", "ابتزاز", "تهديد", "إفشاء")):
            tags.append("#القانون_الجنائي")
        elif any(word in topic_lower for word in ("تصوير", "تسجيل", "خصوصية")):
            tags.append("#الحق_في_الخصوصية")
        lines += ["", " ".join(tags)]
    description = "\\n".join(lines).strip()
    if len(description) < 100:
        raise ValueError("Generated video description is unexpectedly short.")
    return description[:4900]
