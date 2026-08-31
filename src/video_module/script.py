from __future__ import annotations

import re


def _clean(text: str) -> str:
    text = re.sub(r"(?i)\b(?:topic|angle|status|row|post_id)\s*[:=].*?(?=\.|\n|$)", "", text)
    text = re.sub(r"زاوية\s*(?:جديدة|المحتوى)?\s*[:：-]?", "", text)
    text = re.sub(r"اسم\s*الموضوع\s*[:：-]?", "", text)
    return " ".join(text.split()).strip()


def build_script(topic: str, approved_post: str, max_words: int = 120) -> str:
    """Turn the approved post into a short, natural Egyptian-Arabic Reel script.

    Topic/angle are metadata and must never be injected into the spoken script.
    The legal substance comes only from the approved post.
    """
    text = _clean(approved_post)
    if not text:
        raise ValueError("approved_post is required")
    words = text.split()
    body = " ".join(words[:max_words]).strip()
    if not body:
        raise ValueError("approved_post has no usable content")
    return body
