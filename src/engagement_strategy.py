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



def resolve_blogger_article_url(*, topic: str = "", post_text: str = "", explicit_url: str = "") -> str:
    """Resolve a post-specific public Blogger permalink; never guess a slug."""
    candidate = str(explicit_url or "").strip()
    if re.match(r"^https?://(?:www\.)?askmahmoudkhyrat\.blogspot\.com/\d{4}/\d{2}/", candidate, flags=re.I):
        return re.sub(r"[?&]m=1(?:&.*)?$", "", candidate)
    try:
        import requests
        response = requests.get(
            "https://askmahmoudkhyrat.blogspot.com/feeds/posts/default",
            params={"alt": "json", "max-results": "100"},
            headers={"User-Agent": "KhyratLegalContentEngine/1.0"},
            timeout=12,
        )
        response.raise_for_status()
        entries = response.json().get("feed", {}).get("entry", [])
    except Exception as exc:
        print(f"Could not resolve matching Blogger article from public feed: {exc}")
        return BLOGGER_URL

    def terms(value: str) -> set[str]:
        words = re.findall(r"[\w\u0600-\u06FF]{3,}", str(value or "").casefold())
        stop = {"اللي", "على", "من", "في", "عن", "مع", "هذا", "هذه", "ذلك", "التي", "الذي", "بعد", "قبل", "عند", "بين", "كيف", "متى", "هل", "إلى", "الى", "لدى", "كان", "تكون", "يمكن", "بشأن", "حول", "ضمن"}
        return {word for word in words if word not in stop}

    source_terms = terms(str(topic or "") + " " + str(post_text or "")[:1400])
    if not source_terms:
        return BLOGGER_URL
    scored = []
    for entry in entries if isinstance(entries, list) else []:
        title = str(entry.get("title", {}).get("$t", ""))
        title_terms = terms(title)
        if not title_terms:
            continue
        overlap = len(source_terms & title_terms) / len(title_terms)
        coverage = len(source_terms & title_terms) / len(source_terms)
        score = 0.7 * overlap + 0.3 * coverage
        links = entry.get("link", [])
        href = next((str(link.get("href", "")).strip() for link in links if link.get("rel") == "alternate" and link.get("href")), "")
        if href and re.match(r"^https?://askmahmoudkhyrat\.blogspot\.com/\d{4}/\d{2}/", href, flags=re.I):
            scored.append((score, title, href))
    scored.sort(reverse=True)
    if scored and scored[0][0] >= 0.48 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.08):
        print(f"Matched Blogger article for LinkedIn CTA: {scored[0][1]} -> {scored[0][2]}")
        return scored[0][2]
    print("No confident matching Blogger article found; using blog homepage rather than guessing a wrong article.")
    return BLOGGER_URL

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
    # The CTA subject must come from this post, never a hard-coded legal category.
    subject = str(topic or "").strip()[:90] or "الموضوع ده"
    digest = hashlib.sha256((str(post_key or "") + "|" + context).encode("utf-8")).digest()
    # Keep the fixed link comment concise and directly related to the post.
    # Repeated multi-part calls to read, visit, and share can look promotional;
    # the comment should have one clear action and no extra engagement bait.
    variants = [
        f"معلومات وأمثلة عملية عن {subject}: {candidate_url}",
        f"أمثلة عملية وخطوات مرتبطة بـ{subject}: {candidate_url}",
        f"شرح وتفاصيل عملية عن {subject}: {candidate_url}",
        f"معلومات وأمثلة واقعية عن {subject}: {candidate_url}",
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
