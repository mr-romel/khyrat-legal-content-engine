"""Public Mostaql business-category project discovery."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    value = unescape(value).replace("\\/", "/")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    return re.sub(r"\s+", " ", value).strip()


def _legal_score(title: str, description: str) -> int:
    text = f"{title} {description}".lower()
    strong = sum(1 for term in STRONG_TERMS if term in text)
    normal = sum(1 for term in LEGAL_TERMS if term in text)
    if strong == 0:
        return 0
    return min(100, 20 + strong * 12 + normal * 4)


def _add(results: list[dict[str, Any]], seen: set[str], href: str, title: str,
         description: str, limit: int, *, official: bool = False) -> None:
    href = unescape(href).replace("\\/", "/").strip()
    href = href.replace("https://www.mostaql.com/", "https://mostaql.com/")
    href = href.replace("http://www.mostaql.com/", "https://mostaql.com/")
    if href.startswith("http://mostaql.com/"):
        href = "https://mostaql.com/" + href.removeprefix("http://mostaql.com/")
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
    results.append({"platform": "mostaql", "title": title, "description": description or title,
                    "source_url": href, "discovery_score": score})


def parse_projects(text: str, limit: int = 40, *, official: bool = False) -> list[dict[str, Any]]:
    """Extract project URLs from the Business-filter response only."""
    text = unescape(text).replace("\\/", "/")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    patterns = (
        re.compile(r'<a[^>]+href=["\'](?P<href>(?:https?://(?:www\.)?mostaql\.com)?/project(?:s)?/[^"\']+)["\'][^>]*>(?P<body>.*?)</a>', re.I | re.S),
        re.compile(r'\[(?P<title>[^\]]+)\]\((?P<href>(?:https?://(?:www\.)?mostaql\.com)?/project(?:s)?/[^)\s]+)\)', re.I),
        re.compile(r'https?://(?:www\.)?mostaql\.com/project(?:s)?/[A-Za-z0-9][^\s)<>"\']*|/project(?:s)?/[A-Za-z0-9][^\s)<>"\']*', re.I),
    )
    for index, pattern in enumerate(patterns):
        for match in pattern.finditer(text):
            href = match.group("href") if "href" in match.groupdict() else match.group(0).rstrip(".,;:)")
            href = urljoin(BASE_URL, href)
            if index == 1:
                title = match.group("title")
            elif index == 0:
                title = _clean(match.group("body"))
            else:
                window = text[max(0, match.start() - 400):match.start()]
                lines = [line.strip(" #-\t") for line in window.splitlines() if line.strip()]
                title = lines[-1] if lines else href.rsplit("/", 1)[-1].replace("-", " ")
            _add(results, seen, href, title, title, limit, official=official)
            if len(results) >= limit:
                return results
    return results[:limit]


def _reader_url(target_url: str) -> str:
    target = target_url.replace("https://", "", 1).replace("http://", "", 1)
    return "https://r.jina.ai/https://" + target


def _fetch_business_page(timeout: int) -> str:
    """Fetch only the official Business filter; reader is transport, not discovery."""
    candidates = [BUSINESS_FILTER_URL, BUSINESS_FILTER_URL + "?page=1",
                  BUSINESS_FILTER_URL + "?sort=latest", BUSINESS_FILTER_URL + "?sort=latest&page=1"]
    for target in candidates:
        for fetch_url in (target, _reader_url(target), "https://r.jina.ai/http://" + target.removeprefix("https://")):
            try:
                response = requests.get(fetch_url, timeout=min(timeout, 15),
                                        headers={"User-Agent": "Mozilla/5.0 (compatible; KhyratMarketplaceDiscovery/12.0)"})
                if response.ok and response.text.strip():
                    body = response.text
                    if "/project" in body.lower() and (parse_projects(body, 1, official=True) or re.search(r"/project(?:s)?/[A-Za-z0-9]", body, re.I)):
                        return body
            except requests.RequestException:
                continue
    return ""


def _fetch_project_page(url: str, timeout: int) -> str:
    for reader_url in (_reader_url(url), "https://r.jina.ai/http://" + url.removeprefix("https://")):
        try:
            response = requests.get(reader_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            if response.ok and response.text.strip():
                return response.text
        except requests.RequestException:
            continue
    return ""


def _project_is_open_text(text: str) -> bool:
    normalized = _clean(unescape(text)).lower()
    if not normalized:
        return False
    closed_terms = ("حالة المشروع مغلق", "المشروع مغلق", "حالة المشروع: مغلق",
                    "حالة المشروع منتهي", "المشروع منتهي", "تم إغلاق المشروع",
                    "تم التوظيف", "closed", "project closed", "project is closed",
                    "expired", "archived")
    return not any(term in normalized for term in closed_terms)


def _project_is_open(url: str, timeout: int) -> bool:
    return _project_is_open_text(_fetch_project_page(url, timeout))


def validate_live_projects(projects: list[dict[str, Any]], *, limit: int = 10, timeout: int = 8) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for item in projects:
        if len(valid) >= limit:
            break
        page = _fetch_project_page(str(item.get("source_url", "")), timeout)
        if page and _project_is_open_text(page):
            valid.append({**item, "live": True})
    return valid


def discover_mostaql(*, url: str = BASE_URL, limit: int = 10, timeout: int = 20) -> list[dict[str, Any]]:
    """Discover legal opportunities ONLY from Mostaql's Business filter."""
    _ = url
    text = _fetch_business_page(timeout)
    if not text:
        return []
    candidates = parse_projects(text, limit=max(limit * 20, 200), official=True)
    if not candidates:
        return []

    def inspect(item: dict[str, Any]) -> dict[str, Any] | None:
        page = _fetch_project_page(str(item.get("source_url", "")), min(timeout, 8))
        if not page or not _project_is_open_text(page):
            return None
        clean_page = _clean(page)
        title = item["title"]
        heading = re.search(r"(?:^|\n)#{1,3}\s+([^\n]{4,180})", page)
        if heading:
            title = _clean(heading.group(1))[:180]
        score = _legal_score(title, clean_page)
        if score < 24:
            return None
        return {**item, "title": title, "description": clean_page[:4000],
                "discovery_score": score, "live": True,
                "source_filter": BUSINESS_FILTER_URL, "source_kind": "mostaql_business_filter"}

    scored: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(inspect, item) for item in candidates]
        for future in as_completed(futures):
            item = future.result()
            if item:
                scored.append(item)
                if len(scored) >= limit:
                    break
        for future in futures:
            if not future.done():
                future.cancel()
    return sorted(scored, key=lambda x: int(x.get("discovery_score", 0)), reverse=True)[:limit]


def merge_discoveries(existing: list[dict[str, Any]], discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url = {str(item.get("source_url")): item for item in existing if item.get("source_url")}
    for item in discovered:
        key = str(item.get("source_url"))
        if key:
            by_url[key] = {**by_url.get(key, {}), **item}
    return sorted(by_url.values(), key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
