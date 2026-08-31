from __future__ import annotations


def build_script(topic: str, approved_post: str, max_words: int = 120) -> str:
    """Create a concise script from approved content only; no new legal claims."""
    text = " ".join(approved_post.split())
    if not text:
        raise ValueError("approved_post is required")
    words = text.split()
    body = " ".join(words[:max_words])
    if topic.strip() and topic.strip() not in body:
        body = f"{topic.strip()}. {body}"
    return body.strip()
