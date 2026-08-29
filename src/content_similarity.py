from __future__ import annotations

import re
from difflib import SequenceMatcher


DEFAULT_THRESHOLD = 0.72


def normalize_text(text: str) -> str:
    value = (text or "").lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def similarity(a: str, b: str) -> float:
    left = normalize_text(a)
    right = normalize_text(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _ngram_similarity(a: str, b: str, n: int = 3) -> float:
    left = normalize_text(a).split()
    right = normalize_text(b).split()
    if len(left) < n or len(right) < n:
        return similarity(a, b)
    left_grams = {" ".join(left[i:i + n]) for i in range(len(left) - n + 1)}
    right_grams = {" ".join(right[i:i + n]) for i in range(len(right) - n + 1)}
    if not left_grams or not right_grams:
        return 0.0
    return len(left_grams & right_grams) / len(left_grams | right_grams)


def _hook(text: str) -> str:
    normalized = normalize_text(text)
    words = normalized.split()
    return " ".join(words[:28])


def content_similarity(a: str, b: str) -> float:
    """Score semantic/structural text overlap without changing the legal meaning."""
    overall = similarity(a, b)
    hook = similarity(_hook(a), _hook(b))
    grams = _ngram_similarity(a, b)
    return min(1.0, (overall * 0.55) + (hook * 0.25) + (grams * 0.20))


def highest_similarity(candidate: str, previous_posts: list[str], threshold: float = DEFAULT_THRESHOLD) -> tuple[float, str]:
    best_score = 0.0
    best_match = ""
    for previous in previous_posts:
        score = content_similarity(candidate, previous)
        if score > best_score:
            best_score = score
            best_match = previous
    return best_score, best_match


def passes_similarity_gate(candidate: str, previous_posts: list[str], threshold: float = DEFAULT_THRESHOLD) -> bool:
    score, _ = highest_similarity(candidate, previous_posts, threshold)
    return score < threshold


def build_similarity_gate_context(previous_posts: list[str], threshold: float = DEFAULT_THRESHOLD) -> str:
    if not previous_posts:
        return "CONTENT SIMILARITY GATE: no previous post text is available; write naturally."
    excerpts = []
    for index, post in enumerate(previous_posts[-8:], start=1):
        normalized = " ".join((post or "").split())
        excerpts.append(f"{index}. {normalized[:700]}")
    return (
        "CONTENT SIMILARITY GATE\n"
        f"Target maximum similarity: {threshold:.2f}\n"
        "قارن المنشور الجديد داخليًا بهذه المنشورات الأخيرة قبل إخراجه. "
        "إذا كان قريبًا في الصياغة أو ترتيب الأفكار أو الـHook، أعد صياغته قبل الإخراج. "
        "لا تغيّر القاعدة القانونية لمجرد التنويع. لا تنسخ جملًا مميزة من المنشورات السابقة.\n"
        + "\n".join(excerpts)
    )
