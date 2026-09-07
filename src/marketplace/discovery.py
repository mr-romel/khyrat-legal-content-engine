"""Public Mostaql project discovery without account login or submission automation."""
from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import quote_plus, urljoin
import xml.etree.ElementTree as ET

import requests

BASE_URL = "https://mostaql.com/projects"
READER_URL = "https://r.jina.ai/https://mostaql.com/projects"
SEARCH_TERMS = (
    "استشارة قانونية", "صياغة عقد", "مراجعة عقد", "محامي", "محاماة",
    "عقد", "عقود", "اتفاقية", "قانوني", "لائحة قانونية",
)
LEGAL_TERMS = (
    "محامي", "محاماة", "قانون", "قانوني", "قانونية", "عقد", "عقود",
    "صياغة", "مراجعة", "استشارة", "اتفاقية", "لائحة", "سياسة",
    "نزاع", "تجاري", "قضية", "بحث قانوني", "عمل", "عمال",
)
STRONG_TERMS = (
    "محامي", "محاماة", "استشارة قانونية", "صياغة عقد", "مراجعة عقد",
    "عقد", "عقود", "اتفاقية", "قانوني", "قانونية", "لائحة قانونية",
)
OPEN_MARKERS = ("حالة المشروع\n\nمفتوح", "حالة المشروع: مفتوح", "مفتوح")
CLOSED_MARKERS = ("مغلق", "مكتمل", "ملغي", "قيد التنفيذ")


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


def _add(
    results: list[dict[str, Any]],
    seen: set[str],
    href: str,
    title: str,
    description: str,
    limit: int,
) -> None:
    if len(results) >= limit or href in seen or "/project/create" in href:
        return
    title = _clean(title)[:180]
    description = _clean(description)[:4000]
    if not title or not description or len(title) < 4:
        return
    score = _legal_score(title, description)
    if score < 24:
        return
    seen.add(href)
    results.append({
        "platform": "mostaql",
        "title": title,
        "description": description,
        "source_url": href,
        "discovery_score": score,
    })


def parse_projects(text: str, limit: int = 40) -> list[dict[str, Any]]:
    """Parse project cards/links while ignoring surrounding page chrome."""
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    html_pattern = re.compile(
        r'<a[^>]+href=["\'](?P<href>/project/[^"\']+)["\'][^>]*>(?P<body>.*?)</a>',
        re.I | re.S,
    )
    for match in html_pattern.finditer(text):
        body = _clean(match.group("body"))
        href = urljoin(BASE_URL, match.group("href"))
        _add(results, seen, href, body, body, limit)
    md_pattern = re.compile(
        r'\[(?P<title>[^\]]+)\]\((?P<href>https://mostaql\.com/project/[^)]+)\)', re.I
    )
    for match in md_pattern.finditer(text):
        href = match.group("href")
        title = match.group("title")
        context = text[max(0, match.start() - 1800):match.end() + 1800]
        _add(results, seen, href, title, context, limit)
    return results[:limit]


def _bing_projects(limit: int, timeout: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term in SEARCH_TERMS:
        url = "https://www.bing.com/search?format=rss&q=" + quote_plus(
            f"site:mostaql.com/project {term}"
        )
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if not response.ok:
            continue
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            continue
        for item in root.findall(".//item"):
            link = (item.findtext("link") or "").strip()
            title = (item.findtext("title") or "").strip()
            description = (item.findtext("description") or "").strip()
            if "/project/" not in link:
                continue
            _add(results, seen, link, title, description, limit)
            if len(results) >= limit:
                return results
    return results


def _project_is_open(url: str, timeout: int) -> bool:
    """Reject stale/closed projects before they reach the operator dashboard."""
    reader_url = "https://r.jina.ai/http://" + url.removeprefix("https://")
    try:
        response = requests.get(reader_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException:
        return False
    if not response.ok:
        return False
    text = _clean(response.text)
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in CLOSED_MARKERS):
        return False
    return any(marker.lower() in lowered for marker in OPEN_MARKERS)


def validate_live_projects(
    projects: list[dict[str, Any]], *, limit: int = 10, timeout: int = 8
) -> list[dict[str, Any]]:
    """Keep only public project URLs that resolve and still report as open."""
    valid: list[dict[str, Any]] = []
    for item in projects:
        if len(valid) >= limit:
            break
        url = str(item.get("source_url", ""))
        if url and _project_is_open(url, timeout):
            valid.append({**item, "live": True})
    return valid


def discover_mostaql(*, url: str = BASE_URL, limit: int = 10, timeout: int = 20) -> list[dict[str, Any]]:
    """Discover legal projects and return only currently open, resolvable URLs."""
    candidates = _bing_projects(max(limit * 3, 20), timeout)
    if not candidates:
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "KhyratMarketplaceDiscovery/2.0"})
        if response.ok:
            candidates = parse_projects(response.text, limit=max(limit * 3, 20))
        if not candidates:
            reader = requests.get(READER_URL, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            if reader.ok:
                candidates = parse_projects(reader.text, limit=max(limit * 3, 20))
    return validate_live_projects(candidates, limit=limit, timeout=min(timeout, 8))


def merge_discoveries(existing: list[dict[str, Any]], discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url = {str(item.get("source_url")): item for item in existing if item.get("source_url")}
    for item in discovered:
        key = str(item.get("source_url"))
        if key:
            by_url[key] = {**by_url.get(key, {}), **item}
    return sorted(by_url.values(), key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
