"""Mostaql Business-filter discovery with one canonical source boundary."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlsplit

import requests

BASE_URL = "https://mostaql.com/projects/business"
BUSINESS_FILTER_URL = BASE_URL
LEGAL_TERMS = (
    "محامي", "محاماة", "قانون", "قانوني", "قانونية", "عقد", "عقود", "صياغة",
    "استشارة", "استشارات", "اتفاقية", "اتفاقيات", "لائحة", "سياسة", "خصوصية",
    "نزاع", "قضية", "بحث قانوني", "مذكرة", "امتثال", "حوكمة", "تعاقد", "تعاقدات",
    "شروط الاستخدام", "شروط وأحكام", "سياسة الخصوصية", "تجارة إلكترونية",
)
STRONG_TERMS = (
    "محامي", "محاماة", "استشارة قانونية", "استشارات قانونية", "صياغة عقد", "مراجعة عقد",
    "عقد", "عقود", "اتفاقية", "اتفاقيات", "قانوني", "قانونية", "مذكرة قانونية",
    "كتابة قانونية", "بحث قانوني", "شروط وأحكام", "سياسة الخصوصية", "تعاقد", "تعاقدات",
)


def _clean(value: str) -> str:
    value = unquote(unescape(value).replace("\\/", "/"))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    return re.sub(r"\s+", " ", value).strip()


def _legal_score(title: str, description: str) -> int:
    title_text = _clean(title).lower()
    body_text = _clean(description).lower()
    text = f"{title_text} {body_text}"
    strong = sum(1 for term in STRONG_TERMS if term in text)
    normal = sum(1 for term in LEGAL_TERMS if term in text)
    title_strong = sum(1 for term in STRONG_TERMS if term in title_text)
    title_normal = sum(1 for term in LEGAL_TERMS if term in title_text)
    # Generic words such as "مراجعة" or "شركة" must never qualify a project alone.
    if title_strong == 0 and title_normal < 2 and normal < 2:
        return 0
    score = 20 + strong * 10 + normal * 3 + title_strong * 15 + title_normal * 5
    if title_strong:
        score += 15
    return min(100, score)


def _canonical_url(href: str) -> str:
    href = urljoin(BASE_URL, unescape(href).replace("\\/", "/").strip())
    parsed = urlsplit(href)
    host = (parsed.hostname or "").lower()
    if host not in {"mostaql.com", "www.mostaql.com"}:
        return ""
    path = parsed.path.rstrip("/")
    return f"https://mostaql.com{path}" if path else ""


def _is_project_url(href: str) -> bool:
    path = urlsplit(href).path.rstrip("/")
    if path == "/project/create":
        return False
    return bool(re.fullmatch(r"/project/[^/?#\s<>\"']+", path, re.I))


def _add(results: list[dict[str, Any]], seen: set[str], href: str, title: str,
         description: str, limit: int, *, official: bool = False) -> None:
    href = _canonical_url(href)
    if len(results) >= limit or not href or href in seen or not _is_project_url(href):
        return
    title, description = _clean(title)[:180], _clean(description)[:4000]
    if len(title) < 4:
        title = _clean(href.rsplit("/", 1)[-1].replace("-", " "))
    score = _legal_score(title, description)
    if not official and score < 24:
        return
    if official and score < 24:
        score = 1
    seen.add(href)
    results.append({
        "platform": "mostaql", "title": title, "description": description or title,
        "source_url": href, "discovery_score": score,
    })


def parse_projects(text: str, limit: int = 40, *, official: bool = False) -> list[dict[str, Any]]:
    """Extract real /project/<slug> links from the canonical Business response."""
    text = unescape(text).replace("\\/", "/")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    anchor_pattern = re.compile(
        r'<a\b[^>]*?href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<body>.*?)</a>', re.I | re.S
    )
    url_pattern = re.compile(
        r'(?P<href>(?:https?://(?:www\.)?mostaql\.com)?/project/[^/?#\s<>"\']+)', re.I
    )
    for match in anchor_pattern.finditer(text):
        href = _canonical_url(match.group("href"))
        if not href or not _is_project_url(href):
            continue
        body = _clean(match.group("body"))
        _add(results, seen, href, body, body, limit, official=official)
        if len(results) >= limit:
            return results
    for match in url_pattern.finditer(text):
        href = _canonical_url(match.group("href"))
        if not href or not _is_project_url(href):
            continue
        slug = _clean(href.rsplit("/", 1)[-1].replace("-", " "))
        _add(results, seen, href, slug, slug, limit, official=official)
        if len(results) >= limit:
            return results
    return results


def _reader_url(target: str) -> str:
    return "https://r.jina.ai/https://" + target.removeprefix("https://").removeprefix("http://")


def _translate_url(target: str) -> str:
    parts = urlsplit(target)
    path = quote(parts.path, safe="/:")
    query = quote(parts.query, safe="=&%")
    suffix = f"?{query}&" if query else "?"
    return f"https://mostaql-com.translate.goog{path}{suffix}_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en"


def _agentsweb_url(target: str) -> str:
    return "https://agentsweb.org/fetch?url=" + quote(target, safe="")


def _transport_urls(target: str) -> tuple[str, ...]:
    return (target, _reader_url(target), _translate_url(target), _agentsweb_url(target))


def _looks_like_business_response(body: str) -> bool:
    if not body or len(body) < 300:
        return False
    normalized = body.lower()
    return ("mostaql" in normalized or "مستقل" in normalized) and bool(
        re.search(r"/project/[^/?#\s<>\"']+", body, re.I)
    )


def _get(url: str, timeout: int) -> str:
    try:
        response = requests.get(url, timeout=min(timeout, 15), headers={
            "User-Agent": "Mozilla/5.0 (compatible; KhyratMarketplaceDiscovery/24.0)"
        })
        return response.text if response.ok else ""
    except requests.RequestException:
        return ""


def _fetch_business_page(timeout: int) -> str:
    """Fetch only the canonical Business filter; transports never change the source."""
    variants = (
        BUSINESS_FILTER_URL,
        BUSINESS_FILTER_URL + "?sort=latest",
        BUSINESS_FILTER_URL + "?page=1",
    )
    for target in variants:
        for transport in _transport_urls(target):
            body = _get(transport, timeout)
            if _looks_like_business_response(body) and parse_projects(body, 1, official=True):
                return body
    return ""


def _fetch_project_page(url: str, timeout: int) -> str:
    for transport in (_reader_url(url), _translate_url(url), _agentsweb_url(url)):
        body = _get(transport, timeout)
        if body and ("mostaql" in body.lower() or "مستقل" in body.lower()):
            return body
    return ""


def _project_is_open_text(text: str) -> bool:
    normalized = _clean(unescape(text)).lower()
    if not normalized:
        return False
    closed_terms = (
        "حالة المشروع مغلق", "المشروع مغلق", "حالة المشروع: مغلق", "حالة المشروع منتهي",
        "المشروع منتهي", "تم إغلاق المشروع", "تم التوظيف", "closed", "project closed",
        "project is closed", "expired", "archived",
    )
    return not any(term in normalized for term in closed_terms)


def _project_is_open(url: str, page: str | None = None, timeout: int = 8) -> bool:
    body = page if page is not None else _fetch_project_page(url, timeout)
    return bool(body) and _project_is_open_text(body)


def validate_live_projects(projects: list[dict[str, Any]], *, limit: int = 10, timeout: int = 8) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for item in projects:
        if len(valid) >= limit:
            break
        url = str(item.get("source_url", ""))
        page = _fetch_project_page(url, timeout)
        if _project_is_open(url, page, timeout):
            valid.append({**item, "live": True})
    return valid


def discover_mostaql(*, url: str = BASE_URL, limit: int = 10, timeout: int = 20) -> list[dict[str, Any]]:
    """Discover legal opportunities exclusively from the canonical Business filter."""
    _ = url
    raw = _fetch_business_page(timeout)
    # Inspect the whole current Business page, not just the first 20 generic projects.
    candidates = parse_projects(raw, limit=max(limit * 20, 200), official=True) if raw else []
    if not candidates:
        return []

    def inspect(item: dict[str, Any]) -> dict[str, Any] | None:
        page = _fetch_project_page(str(item["source_url"]), min(timeout, 8))
        if not page or not _project_is_open(str(item["source_url"]), page):
            return None
        clean_page = _clean(page)
        title = _clean(item["title"])
        heading = re.search(r"(?:^|\n)#{1,3}\s+([^\n]{4,180})", page)
        if heading:
            title = _clean(heading.group(1))[:180]
        score = _legal_score(title, clean_page)
        if score < 24:
            return None
        return {
            **item,
            "title": title,
            "description": clean_page[:4000],
            "discovery_score": score,
            "live": True,
            "source_filter": BUSINESS_FILTER_URL,
            "source_kind": "mostaql_business_filter",
        }

    scored: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(inspect, item) for item in candidates]
        for future in as_completed(futures):
            item = future.result()
            if item:
                scored.append(item)
    return sorted(scored, key=lambda x: int(x.get("discovery_score", 0)), reverse=True)[:limit]


def merge_discoveries(existing: list[dict[str, Any]], discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url = {str(item.get("source_url")): item for item in existing if item.get("source_url")}
    for item in discovered:
        key = str(item.get("source_url"))
        if key:
            by_url[key] = {**by_url.get(key, {}), **item}
    return sorted(by_url.values(), key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
