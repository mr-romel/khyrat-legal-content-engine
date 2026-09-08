"""Public Mostaql project discovery without account login or submission automation."""
from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import quote_plus, urljoin
import xml.etree.ElementTree as ET

import requests

BASE_URL = "https://mostaql.com/projects"
LEGAL_SKILL_URLS = (
    "https://mostaql.com/projects/skill/legal",
    "https://mostaql.com/projects/skill/contracts",
    "https://mostaql.com/projects/skill/legal-writing",
    "https://mostaql.com/projects/skill/legal-research",
)
SEARCH_TERMS = (
    "استشارة قانونية", "صياغة عقد", "مراجعة عقد", "محامي", "محاماة",
    "عقد", "عقود", "اتفاقية", "قانوني", "قانونية", "كتابة قانونية",
    "مذكرة قانونية", "بحث قانوني", "قانون العمل", "شؤون قانونية",
    "شروط الاستخدام", "سياسة الخصوصية", "شروط وأحكام", "نزاع تجاري",
)
LEGAL_TERMS = (
    "محامي", "محاماة", "قانون", "قانوني", "قانونية", "عقد", "عقود",
    "صياغة", "مراجعة", "استشارة", "استشارات", "اتفاقية", "اتفاقيات",
    "لائحة", "سياسة", "شروط الاستخدام", "شروط وأحكام", "خصوصية",
    "نزاع", "تجاري", "شركة", "شركات", "قضية", "بحث قانوني", "مذكرة",
    "عمل", "عمال", "وظائف", "امتثال", "حوكمة", "تجارة إلكترونية",
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
        "platform": "mostaql", "title": title,
        "description": description or title, "source_url": href,
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


def _bing_projects(limit: int, timeout: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term in SEARCH_TERMS:
        url = "https://www.bing.com/search?format=rss&q=" + quote_plus(f"site:mostaql.com/project {term}")
        try:
            response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        except requests.RequestException:
            continue
        if not response.ok:
            continue
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            continue
        for item in root.findall(".//item"):
            link = (item.findtext("link") or "").strip()
            if "/project/" not in link:
                continue
            _add(results, seen, link, (item.findtext("title") or "").strip(),
                 (item.findtext("description") or "").strip(), limit)
            if len(results) >= limit:
                return results
    return results


def _fetch_skill_page(skill_url: str, timeout: int) -> str:
    """Fetch a public skill page; fall back to Jina when Mostaql blocks raw HTTP."""
    try:
        response = requests.get(skill_url, timeout=timeout,
                                headers={"User-Agent": "KhyratMarketplaceDiscovery/7.0"})
        if response.ok and "/project/" in response.text:
            return response.text
    except requests.RequestException:
        pass
    reader_url = "https://r.jina.ai/http://" + skill_url.removeprefix("https://")
    try:
        response = requests.get(reader_url, timeout=min(timeout, 15),
                                headers={"User-Agent": "Mozilla/5.0"})
        if response.ok:
            return response.text
    except requests.RequestException:
        pass
    return ""


def _official_skill_projects(limit: int, timeout: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for skill_url in LEGAL_SKILL_URLS:
        text = _fetch_skill_page(skill_url, timeout)
        if not text:
            continue
        for item in parse_projects(text, limit=limit, official=True):
            href = str(item.get("source_url", ""))
            if href and href not in seen:
                seen.add(href)
                results.append({**item, "live": True, "source_kind": "official_open_listing"})
                if len(results) >= limit:
                    return results
    return results


def _project_is_open(url: str, timeout: int) -> bool:
    """Reject stale/closed projects for fallback sources."""
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
    return bool(re.search(r"(?:^|[|•\-])\s*(مفتوح|open)\s*(?:$|[|•\-])",
                          normalized, re.I | re.M))


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
    """Discover currently open legal projects from public Mostaql sources."""
    official = _official_skill_projects(max(limit * 3, 30), timeout)
    if official:
        return official[:limit]
    candidates = _bing_projects(max(limit * 4, 30), timeout)
    if not candidates:
        try:
            response = requests.get(url, timeout=timeout,
                                    headers={"User-Agent": "KhyratMarketplaceDiscovery/7.0"})
            if response.ok:
                candidates = parse_projects(response.text, limit=max(limit * 4, 30))
        except requests.RequestException:
            candidates = []
    return validate_live_projects(candidates, limit=limit, timeout=min(timeout, 8))


def merge_discoveries(existing: list[dict[str, Any]], discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url = {str(item.get("source_url")): item for item in existing if item.get("source_url")}
    for item in discovered:
        key = str(item.get("source_url"))
        if key:
            by_url[key] = {**by_url.get(key, {}), **item}
    return sorted(by_url.values(), key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
