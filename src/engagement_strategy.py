from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
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
    blog_url: str = "",
) -> str:
    """Return a relevant, varied Blogger CTA using the matching article URL when available."""
    platform_name = str(platform or "facebook").strip().lower()
    candidate_url = str(blog_url or "").strip()
    if not re.match(r"^https?://(?:www\.)?askmahmoudkhyrat\.blogspot\.com(?:/|$)", candidate_url, flags=re.I):
        candidate_url = BLOGGER_URL
    candidate_url = re.sub(r"[?&]m=1(?:&.*)?$", "", candidate_url)
    if platform_name == "facebook":
        parts = urlsplit(candidate_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update({
            "utm_source": "facebook",
            "utm_medium": "organic_social",
            "utm_campaign": "legal_reels",
            "utm_content": re.sub(r"[^A-Za-z0-9_-]", "", str(post_key or ""))[:80] or "facebook_post",
        })
        candidate_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
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
    # Keep the fixed link comment concise and directly related to the post.
    # Repeated multi-part calls to read, visit, and share can look promotional;
    # the comment should have one clear action and no extra engagement bait.
    variants = [
        f"التفاصيل عن {subject} على مدونة اسأل محمود: {candidate_url}",
        f"للاطلاع على تفاصيل {subject} والأمثلة العملية: {candidate_url}",
        f"لو حابب تعرف تفاصيل أكثر عن {subject}، اقرأ هنا: {candidate_url}",
        f"معلومات إضافية مرتبطة بـ{subject} في مدونة اسأل محمود: {candidate_url}",
    ]
    return variants[digest[0] % len(variants)]


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


def remove_blogger_link(text: str) -> str:
    """Remove Blogger URLs from replies and contextual comments; dedicated CTA comments bypass this."""
    value = str(text or "")
    value = re.sub(
        r"(?i)(?:https?://)?(?:www\.)?askmahmoudkhyrat\.blogspot\.com(?:/[^\s]*)?",
        "",
        value,
    )
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = re.sub(r"\s+([،,؛;:.!?؟])", r"\1", value)
    return value.strip()


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
