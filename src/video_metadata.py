from __future__ import annotations

import re
from urllib.parse import urlparse

BLOGGER_HOST = "askmahmoudkhyrat.blogspot.com"
WHATSAPP_URL = "https://wa.me/201022718375"


def _clean(value: str, limit: int = 700) -> str:
    text = re.sub(r"https?://\\S+", "", str(value or ""))
    text = re.sub(r"\\s+", " ", text).strip()
    return text[:limit].rstrip(" ،؛:.")


def _valid_article_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname == BLOGGER_HOST and parsed.path not in {"", "/"}


def build_video_description(*, topic: str, post: str, script: str, article_url: str = "", platform: str = "facebook") -> str:
    """Create a substantive, topic-specific public description from the approved post and Reel script."""
    topic = _clean(topic, 180) or "معلومة قانونية"
    source = _clean(post, 1100)
    narration = _clean(script, 650)
    platform = str(platform or "").strip().lower()
    if platform not in {"facebook", "youtube"}:
        raise ValueError("platform must be facebook or youtube")

    # Prefer the actual narrated explanation, then add a concise source-grounded context.
    body = narration or source
    if not body:
        raise ValueError("Cannot publish a video description without approved topic content.")
    if len(body) > 650:
        body = body[:647].rsplit(" ", 1)[0] + "..."

    lines = [
        f"🎬 {topic}",
        "",
        f"في الفيديو ده بنشرح {topic} بشكل عملي، وإيه النقاط القانونية اللي لازم تتراجع قبل اتخاذ أي قرار.",
        body,
    ]
    if _valid_article_url(article_url):
        lines += ["", "📖 اقرأ المقال الكامل المرتبط بنفس الموضوع:", str(article_url).strip()]
    lines += [
        "",
        "للاستفسارات القانونية: https://wa.me/201022718375",
        "المحتوى للتوعية القانونية العامة، والتقييم النهائي بيتوقف على تفاصيل كل حالة ومستنداتها.",
    ]
    if platform == "youtube":
        tags = ["#معلومة_قانونية", "#اسأل_محمود"]
        topic_lower = topic.lower()
        if any(word in topic_lower for word in ("عمل", "عامل", "عمال")):
            tags.append("#حقوق_العمال")
        elif any(word in topic_lower for word in ("شركة", "شركات", "تجاري", "شراكة")):
            tags.append("#قانون_الشركات")
        elif any(word in topic_lower for word in ("أسرة", "طلاق", "نفقة", "حضانة")):
            tags.append("#الأحوال_الشخصية")
        elif any(word in topic_lower for word in ("جنائي", "جريمة", "ابتزاز")):
            tags.append("#القانون_الجنائي")
        lines += ["", " ".join(tags)]
    description = "\\n".join(lines).strip()
    if len(description) < 100:
        raise ValueError("Generated video description is unexpectedly short.")
    return description[:4900]
