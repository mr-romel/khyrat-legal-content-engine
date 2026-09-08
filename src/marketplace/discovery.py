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
)
READER_URL = "https://r.jina.ai/https://mostaql.com/projects/skill/legal"
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


def _add(results: list[dict[str, Any]], seen: set[str], href: str, title: str, description: str, limit: int) -> None:
    if len(results) >= limit or href in seen or "/project/create" in href:
        return
    title = _clean(title)[:180]
    description = _clean(description)[:4000]
    if not title or len(title) < 4:
        return
    score = _legal_score(title, description)
    if score < 24:
        return
    seen.add(href)
    results.append({"platform": "mostaql", "title": title, "description": description or title, "source_url": href, "discovery_score": score})


def parse_projects(text: str, limit: int = 40) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    html_pattern = re.compile(r'<a[^>]+href=["\'](?P<href>/project/[^"\']+)["\'][^>]*>(?P<body>.*?)</a>', re.I | re.S)
    for match in html_pattern.finditer(text):
        body = _clean(match.group("body"))
        href = urljoin(BASE_URL, match.group("href"))
        context = text[max(0, match.start() - 2500):min(len(text), match.end() + 3500)]
        _add(results, seen, href, body, context, limit)
        if len(results) >= limit:
            return results
    md_pattern = re.compile(r'\[(?P<title>[^\]]+)\]\((?P<href>https://mostaql\.com/project/[^)]+)\)', re.I)
    for match in md_pattern.finditer(text):
        _add(results, seen, match.group("href"), match.group("title"), text[max(0, match.start() - 2500):match.end() + 3500], limit)
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
            _add(results, seen, link, (item.findtext("title") or "").strip(), (item.findtext("description") or "").strip(), limit)
            if len(results) >= limit:
                return results
    return results


def _official_skill_projects(limit: int, timeout: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for skill_url in LEGAL_SKILL_URLS:
        try:
            response = requests.get(skill_url, timeout=timeout, headers={"User-Agent": "KhyratMarketplaceDiscovery/3.0"})
        except requests.RequestException:
            continue
        if not response.ok:
            continue
        for item in parse_projects(response.text, limit=limit):
            href = str(item.get("source_url", ""))
            if href and href not in seen:
                seen.add(href)
                results.append(item)
                if len(results) >= limit:
                    return results
    return results


def _project_is_open(url: str, timeout: int) -> bool:
    """Reject stale/closed projects while tolerating reader formatting changes."""
    reader_url = "https://r.jina.ai/http://" + url.removeprefix("https://")
    try:
        response = requests.get(reader_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException:
        return False
    if not response.ok:
        return False
    raw = unescape(response.text)
    normalized = _clean(raw).lower()
    # Jina can render the same field as Arabic, English, with punctuation,
    # or with Markdown/newline separators. Check the local status field rather
    # than requiring one exact string.
    status_patterns = (
        r"حالة\s*المشروع\s*[:：-]?\s*مفتوح(?:\s|$)",
        r"حالة\s*المشروع.{0,80}\bمفتوح\b",
        r"project\s*status\s*[:：-]?\s*open(?:\s|$)",
        r"status.{0,50}\bopen\b",
    )
    if any(re.search(pattern, normalized, re.I | re.S) for pattern in status_patterns):
        return True
    # Some reader responses expose the status as a standalone badge.
    standalone = re.search(r"(?:^|[|•\-])\s*(مفتوح|open)\s*(?:$|[|•\-])", normalized, re.I | re.M)
    if standalone:
        return True
    return False


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
    candidates = _official_skill_projects(max(limit * 3, 30), timeout)
    if not candidates:
        candidates = _bing_projects(max(limit * 4, 30), timeout)
    if not candidates:
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "KhyratMarketplaceDiscovery/3.0"})
        if response.ok:
            candidates = parse_projects(response.text, limit=max(limit * 4, 30))
    if not candidates:
        reader = requests.get(READER_URL, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if reader.ok:
            candidates = parse_projects(reader.text, limit=max(limit * 4, 30))
    return validate_live_projects(candidates, limit=limit, timeout=min(timeout, 8))


def merge_discoveries(existing: list[dict[str, Any]], discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url = {str(item.get("source_url")): item for item in existing if item.get("source_url")}
    for item in discovered:
        key = str(item.get("source_url"))
        if key:
            by_url[key] = {**by_url.get(key, {}), **item}
    return sorted(by_url.values(), key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
