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
SEARCH_TERMS = ("قانون", "محاماة", "عقد", "صياغة عقد", "استشارة قانونية", "مراجعة عقد")
LEGAL_TERMS = (
    "محامي", "محاماة", "قانون", "قانوني", "قانونية", "عقد", "عقود",
    "صياغة", "مراجعة", "استشارة", "شركات", "شركة", "عمل", "عمال",
    "اتفاقية", "لائحة", "سياسة", "نزاع", "تجاري", "قضية", "بحث قانوني",
)


def _clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    return re.sub(r"\s+", " ", unescape(value)).strip()


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
    results.append({"platform": "mostaql", "title": title, "description": body[:4000], "source_url": href, "discovery_score": score})


def parse_projects(text: str, limit: int = 40) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    html_pattern = re.compile(r'<a[^>]+href=["\'](?P<href>/project/[^"\']+)["\'][^>]*>(?P<body>.*?)</a>', re.I | re.S)
    for match in html_pattern.finditer(text):
        _add(results, seen, urljoin(BASE_URL, match.group("href")), match.group("body"), limit)
    md_pattern = re.compile(r'\[[^\]]*\]\((?P<href>https://mostaql\.com/project/[^)]+)\)')
    for match in md_pattern.finditer(text):
        _add(results, seen, match.group("href"), text[max(0, match.start() - 2500):match.end() + 2500], limit)
    return results[:limit]


def _bing_projects(limit: int, timeout: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term in SEARCH_TERMS:
        url = "https://www.bing.com/search?format=rss&q=" + quote_plus(f"site:mostaql.com/project {term}")
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
            _add(results, seen, link, f"{title} {description}", limit)
            if len(results) >= limit:
                return results
    return results


def discover_mostaql(*, url: str = BASE_URL, limit: int = 40, timeout: int = 20) -> list[dict[str, Any]]:
    headers = {"User-Agent": "KhyratMarketplaceDiscovery/1.0"}
    response = requests.get(url, timeout=timeout, headers=headers)
    if response.ok:
        found = parse_projects(response.text, limit=limit)
        if found:
            return found
    if url == BASE_URL and response.status_code in {403, 429}:
        reader = requests.get(READER_URL, timeout=timeout, headers=headers)
        if reader.ok:
            found = parse_projects(reader.text, limit=limit)
            if found:
                return found
        return _bing_projects(limit, timeout)
    response.raise_for_status()
    return []


def merge_discoveries(existing: list[dict[str, Any]], discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url = {str(item.get("source_url")): item for item in existing if item.get("source_url")}
    for item in discovered:
        key = str(item.get("source_url"))
        if key:
            by_url[key] = {**by_url.get(key, {}), **item}
    return sorted(by_url.values(), key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
