"""Public Mostaql business-category project discovery."""
from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

import requests

BASE_URL = "https://mostaql.com/projects/business"
BUSINESS_FILTER_URL = BASE_URL

LEGAL_TERMS = (
    "محامي", "محاماة", "قانون", "قانوني", "قانونية", "عقد", "عقود",
    "صياغة", "مراجعة", "استشارة", "استشارات", "اتفاقية", "اتفاقيات",
    "لائحة", "سياسة", "شروط الاستخدام", "شروط وأحكام", "خصوصية",
    "نزاع", "تجاري", "شركة", "شركات", "قضية", "بحث قانوني", "مذكرة",
    "عمل", "عمال", "امتثال", "حوكمة", "تجارة إلكترونية",
)
STRONG_TERMS = (
    "محامي", "محاماة", "استشارة قانونية", "صياغة عقد", "مراجعة عقد",
    "عقد", "عقود", "اتفاقية", "قانوني", "قانونية", "مذكرة قانونية",
    "كتابة قانونية", "بحث قانوني", "شروط وأحكام", "سياسة الخصوصية",
)


def _clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _legal_score(title: str, description: str) -> int:
    text = f"{title} {description}".lower()
    strong = sum(1 for term in STRONG_TERMS if term in text)
    normal = sum(1 for term in LEGAL_TERMS if term in text)
    if strong == 0:
        return 0
    return min(100, 20 + strong * 12 + normal * 4)


def _add(results: list[dict[str, Any]], seen: set[str], href: str, title: str,
         description: str, limit: int, *, official: bool = False) -> None:
    if len(results) >= limit or href in seen or "/project/create" in href:
        return
    title = _clean(title)[:180]
    description = _clean(description)[:4000]
    if not title or len(title) < 4:
        return
    score = _legal_score(title, description)
    if not official and score < 24:
        return
    if official and score < 24:
        score = 60
    seen.add(href)
    results.append({
        "platform": "mostaql",
        "title": title,
        "description": description or title,
        "source_url": href,
        "discovery_score": score,
    })


def parse_projects(text: str, limit: int = 40, *, official: bool = False) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    html_pattern = re.compile(
        r'<a[^>]+href=["\'](?P<href>/project/[^"\']+)["\'][^>]*>(?P<body>.*?)</a>',
        re.I | re.S,
    )
    for match in html_pattern.finditer(text):
        body = _clean(match.group("body"))
        href = urljoin(BASE_URL, match.group("href"))
        _add(results, seen, href, body, body, limit, official=official)
        if len(results) >= limit:
            return results

    md_pattern = re.compile(
        r'\[(?P<title>[^\]]+)\]\((?P<href>(?:https?://mostaql\.com)?/project/[^)]+)\)',
        re.I,
    )
    for match in md_pattern.finditer(text):
        href = urljoin(BASE_URL, match.group("href"))
        title = _clean(match.group("title"))
        _add(results, seen, href, title, title, limit, official=official)
        if len(results) >= limit:
            break

    if len(results) < limit:
        raw_pattern = re.compile(r'https?://mostaql\.com/project/[A-Za-z0-9][^\s)<>"\']*', re.I)
        for match in raw_pattern.finditer(text):
            href = match.group(0).rstrip(".,;:)")
            if href in seen:
                continue
            window = text[max(0, match.start() - 220):match.start()]
            lines = [line.strip(" #-\t") for line in window.splitlines() if line.strip()]
            title = _clean(lines[-1] if lines else href.rsplit("/", 1)[-1].replace("-", " "))
            _add(results, seen, href, title, title, limit, official=official)
            if len(results) >= limit:
                break
    return results[:limit]


def _fetch_business_page(timeout: int) -> str:
    """Fetch only the public Mostaql business filter; use Jina if raw HTTP is blocked."""
    try:
        response = requests.get(
            BUSINESS_FILTER_URL,
            timeout=timeout,
            headers={"User-Agent": "KhyratMarketplaceDiscovery/8.0"},
        )
        if response.ok and "/project/" in response.text:
            return response.text
    except requests.RequestException:
        pass

    reader_url = "https://r.jina.ai/http://" + BUSINESS_FILTER_URL.removeprefix("https://")
    try:
        response = requests.get(
            reader_url,
            timeout=min(timeout, 15),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if response.ok:
            return response.text
    except requests.RequestException:
        pass
    return ""


def _project_is_open(url: str, timeout: int) -> bool:
    """Reject stale/closed projects."""
    reader_url = "https://r.jina.ai/http://" + url.removeprefix("https://")
    try:
        response = requests.get(reader_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException:
        return False
    if not response.ok:
        return False
    normalized = _clean(unescape(response.text)).lower()
    patterns = (
        r"حالة\s*المشروع\s*[:：-]?\s*مفتوح(?:\s|$)",
        r"حالة\s*المشروع.{0,80}\bمفتوح\b",
        r"project\s*status\s*[:：-]?\s*open(?:\s|$)",
        r"status.{0,50}\bopen\b",
    )
    if any(re.search(pattern, normalized, re.I | re.S) for pattern in patterns):
        return True
    return bool(re.search(r"(?:^|[|•\-])\s*(مفتوح|open)\s*(?:$|[|•\-])", normalized, re.I | re.M))


def validate_live_projects(projects: list[dict[str, Any]], *, limit: int = 10, timeout: int = 8) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for item in projects:
        if len(valid) >= limit:
            break
        url = str(item.get("source_url", ""))
        if url and _project_is_open(url, timeout):
            valid.append({**item, "live": True})
    return valid


def discover_mostaql(*, url: str = BASE_URL, limit: int = 10, timeout: int = 20) -> list[dict[str, Any]]:
    """Discover open legal opportunities ONLY from Mostaql's Business filter."""
    if url != BUSINESS_FILTER_URL:
        url = BUSINESS_FILTER_URL
    text = _fetch_business_page(timeout)
    if not text:
        return []

    # The source itself is the Business filter. Legal relevance is applied on top.
    candidates = parse_projects(text, limit=max(limit * 4, 40))
    live = validate_live_projects(candidates, limit=limit, timeout=min(timeout, 8))
    for item in live:
        item["source_filter"] = BUSINESS_FILTER_URL
        item["source_kind"] = "mostaql_business_filter"
    return live


def merge_discoveries(existing: list[dict[str, Any]], discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url = {str(item.get("source_url")): item for item in existing if item.get("source_url")}
    for item in discovered:
        key = str(item.get("source_url"))
        if key:
            by_url[key] = {**by_url.get(key, {}), **item}
    return sorted(by_url.values(), key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
