from __future__ import annotations


def build_script(topic: str, approved_post: str, max_words: int = 180) -> str:
    """Create a bounded script from approved content only.

    This is intentionally provider-neutral. An external AI provider may later implement
    the same contract; this module never calls the Core Gemini client directly.
    """
    text = " ".join(approved_post.split())
    words = text.split()
    body = " ".join(words[:max_words])
    if topic.strip() and topic.strip() not in body:
        return f"{topic.strip()}. {body}".strip()
    return body
