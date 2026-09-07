"""Public Mostaql project discovery without account login or submission automation."""
from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

import requests

BASE_URL = "https://mostaql.com/projects"
READER_URL = "https://r.jina.ai/https://mostaql.com/projects"
LEGAL_TERMS = (
    "محامي", "محاماة", "قانون", "قانوني", "قانونية", "عقد", "عقود",
    "صياغة", "مراجعة", "استشارة", "شركات", "شركة", "عمل", "عمال",
    "اتفاقية", "لائحة", "سياسة", "نزاع", "تجاري", "قضية", "بحث قانوني",
)


def _clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _legal_score(title: str, description: str) -> int:
    text = f"{title} {description}".lower()
    return min(100, 10 + sum(8 for term in LEGAL_TERMS if term in text))


def _add(results: list[dict[str, Any]], seen: set[str], href: str, body: str, limit: int) -> None:
    if len(results) >= limit or href in seen or "/project/create" in href:
        return
    body = _clean(body)
    if not body or len(body) < 4:
        return
    title = body.split("#", 1)[0].strip()[:180].rstrip()
    score = _legal_score(title, body)
    if score < 18:
        return
    seen.add(href)
    results.append({
        "platform": "mostaql",
        "title": title,
        "description": body[:4000],
        "source_url": href,
        "discovery_score": score,
    })


def parse_projects(html: str, limit: int = 40) -> list[dict[str, Any]]:
    """Extract legal-fit public project cards from HTML or Reader markdown."""
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    html_pattern = re.compile(r'<a[^>]+href=["\'](?P<href>/project/[^"\']+)["\'][^>]*>(?P<body>.*?)</a>', re.I | re.S)
    for match in html_pattern.finditer(html):
        _add(results, seen, urljoin(BASE_URL, match.group("href")), match.group("body"), limit)
        if len(results) >= limit:
            return results
    md_pattern = re.compile(r'\[[^\]]*\]\((?P<href>https://mostaql\.com/project/[^)]+)\)')
    for match in md_pattern.finditer(html):
        start = max(0, match.start() - 3000)
        end = min(len(html), match.end() + 3000)
        _add(results, seen, match.group("href"), html[start:end], limit)
        if len(results) >= limit:
            break
    return results


def discover_mostaql(*, url: str = BASE_URL, limit: int = 40, timeout: int = 20) -> list[dict[str, Any]]:
    """Read public projects; fall back to Jina Reader when Mostaql blocks cloud IPs."""
    headers = {"User-Agent": "KhyratMarketplaceDiscovery/1.0"}
    response = requests.get(url, timeout=timeout, headers=headers)
    if response.ok:
        return parse_projects(response.text, limit=limit)
    if url == BASE_URL and response.status_code in {403, 429}:
        reader = requests.get(READER_URL, timeout=timeout, headers=headers)
        reader.raise_for_status()
        return parse_projects(reader.text, limit=limit)
    response.raise_for_status()
    return []


def merge_discoveries(existing: list[dict[str, Any]], discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url = {str(item.get("source_url")): item for item in existing if item.get("source_url")}
    for item in discovered:
        key = str(item.get("source_url"))
        if key:
            by_url[key] = {**by_url.get(key, {}), **item}
    return sorted(by_url.values(), key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
