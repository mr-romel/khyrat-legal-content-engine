from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Iterable

from social_content import sanitize_social_copy

MIN_COMMENTS = 3
MAX_COMMENTS = 7
COMMENT_INTERVAL_MINUTES = 15
BLOGGER_URL = "https://askmahmoudkhyrat.blogspot.com/"


def blog_cta_comment(
    platform: str = "facebook",
    *,
    topic: str = "",
    post_text: str = "",
    post_key: str = "",
) -> str:
    """Return a relevant, varied Blogger CTA instead of repeating one identical link comment."""
    platform_name = str(platform or "facebook").strip().lower()
    context = " ".join((str(topic or "") + " " + str(post_text or "")[:700]).split())
    lowered = context.casefold()
    if any(word in lowered for word in ("إيجار", "إيجارات", "مالك", "مستأجر")):
        subject = "موضوع الإيجارات"
    elif any(word in lowered for word in ("عمل", "عامل", "موظف", "فصل", "مرتب", "إجاز")):
        subject = "موضوع قانون العمل"
    elif any(word in lowered for word in ("شركة", "شركات", "عقد", "عقود")):
        subject = "العقود والشركات"
    elif any(word in lowered for word in ("ورثة", "ميراث", "تركة")):
        subject = "موضوع الميراث"
    else:
        subject = str(topic or "").strip()[:90] or "الموضوع القانوني"

    digest = hashlib.sha256((str(post_key or "") + "|" + context).encode("utf-8")).digest()
    variants = [
        f"للتفاصيل العملية والمصادر المرتبطة بـ{subject}، تقدر تكمل القراءة في مدونة اسأل محمود: {BLOGGER_URL}",
        f"لو محتاج تتوسع في {subject}، جمعنا شروحات ومعلومات إضافية على مدونة اسأل محمود: {BLOGGER_URL}",
        f"الموضوع له تفاصيل مهمة؛ اقرأ الشرح الكامل عن {subject} على مدونة اسأل محمود: {BLOGGER_URL}",
        f"للمزيد من المعلومات والأمثلة العملية في {subject}، زور مدونة اسأل محمود: {BLOGGER_URL}",
    ]
    chosen = variants[digest[0] % len(variants)]
    if platform_name == "linkedin":
        return chosen + " ويمكنك مشاركة الرابط مع زميل قد يستفيد منه"
    return chosen + " ولو شايفه مفيد، شاركه مع حد ممكن يستفيد"


def blog_cta_due(publication_rank: int) -> bool:
    """Include the fixed blog CTA in every eligible published post."""
    try:
        rank = int(publication_rank)
    except (TypeError, ValueError):
        return False
    return rank > 0


def find_cta_event(events: Iterable[dict], event_id: str) -> dict | None:
    """Find the dedicated fixed-CTA event, not a variable comment that mentions the blog."""
    wanted = str(event_id or "").strip()
    if not wanted:
        return None
    return next(
        (
            event for event in events
            if str(event.get("event_id", "")).strip() == wanted
            and str(event.get("action", "")).strip().upper() == "COMMENT"
        ),
        None,
    )


def choose_comment_count(post_key: str) -> int:
    """Deterministically select 3-7 comments per post, varying by post."""
    key = str(post_key or "").strip().encode("utf-8")
    if not key:
        return MIN_COMMENTS
    digest = hashlib.sha256(key).digest()
    return MIN_COMMENTS + (digest[0] % (MAX_COMMENTS - MIN_COMMENTS + 1))


def comment_schedule_times(start: datetime, count: int) -> list[datetime]:
    count = max(MIN_COMMENTS, min(MAX_COMMENTS, int(count)))
    return [start + timedelta(minutes=COMMENT_INTERVAL_MINUTES * i) for i in range(count)]


def comment_schedule_offsets(count: int) -> list[int]:
    count = max(MIN_COMMENTS, min(MAX_COMMENTS, int(count)))
    return [COMMENT_INTERVAL_MINUTES * i for i in range(count)]


def normalize_comment(text: str) -> str:
    value = sanitize_social_copy(str(text or ""))
    value = re.sub(r"\\s+", " ", value).strip()
    value = re.sub(r"[.。]+$", "", value).rstrip()
    return value


def normalize_comments(values: Iterable[str], count: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = normalize_comment(item)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
        if len(result) == count:
            break
    return result
