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


def blog_cta_comment(platform: str = "facebook") -> str:
    """A contextual, reader-first CTA used periodically as one queued comment."""
    if str(platform or "").strip().lower() == "linkedin":
        return (
            "للمتابعة والاطلاع على شروحات ومقالات قانونية عملية بتفصيل أكبر، "
            "يمكنك زيارة مدونة «اسأل محمود». ننشر فيها معلومات وأمثلة تساعد على فهم "
            "الحقوق والإجراءات قبل اتخاذ القرار: " + BLOGGER_URL
        )
    return (
        "لو حابب تتابع معلومات قانونية أوضح وتقرأ مقالات وشروحات عملية بتفصيل أكبر، "
        "زور مدونة «اسأل محمود»؛ بننشر فيها موضوعات وأمثلة تساعدك تفهم حقوقك والخطوات "
        "القانونية المناسبة: " + BLOGGER_URL
    )


def blog_cta_due(publication_rank: int) -> bool:
    """Include the blog CTA on every third published post, not every post."""
    try:
        rank = int(publication_rank)
    except (TypeError, ValueError):
        return False
    return rank > 0 and rank % 3 == 0


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
