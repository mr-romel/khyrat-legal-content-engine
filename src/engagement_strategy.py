from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Iterable

MIN_COMMENTS = 5
MAX_COMMENTS = 8
COMMENT_INTERVAL_MINUTES = 15


def choose_comment_count(post_key: str) -> int:
    """Deterministically select 5-8 comments per post, varying by post."""
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
    value = re.sub(r"\\s+", " ", str(text or "").strip())
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
