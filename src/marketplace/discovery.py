"""Public Mostaql project discovery without account login or submission automation."""
from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

import requests

BASE_URL = "https://mostaql.com/projects"
LEGAL_TERMS = (
    "محامي", "محاماة", "قانون", "قانوني", "قانونية", "عقد", "عقود",
    "صياغة", "مراجعة", "استشارة", "شركات", "شركة", "عمل", "عمال",
    "اتفاقية", "لائحة", "سياسة", "نزاع", "تجاري", "قضية", "بحث قانوني",
)


def _clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _legal_score(title: str, description: str) -> int:
    text = f"{title} {description}".lower()
    return min(100, 10 + sum(8 for term in LEGAL_TERMS if term in text))


def parse_projects(html: str, limit: int = 40) -> list[dict[str, Any]]:
    """Extract public project cards from Mostaql HTML.

    The parser is intentionally conservative: only project links are accepted,
    and the page text is kept as the public source description.
    """
    pattern = re.compile(
        r'<a[^>]+href=["\'](?P<href>/project/[^"\']+)["\'][^>]*>(?P<body>.*?)</a>',
        re.I | re.S,
    )
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for match in pattern.finditer(html):
        href = urljoin(BASE_URL, match.group("href"))
        if href in seen or "/project/create" in href:
            continue
        body = _clean(match.group("body"))
        if not body or len(body) < 4:
            continue
        title = body.split("#", 1)[0].strip()
        if len(title) > 180:
            title = title[:180].rstrip()
        score = _legal_score(title, body)
        if score < 18:
            continue
        seen.add(href)
        results.append({
            "platform": "mostaql",
            "title": title,
            "description": body[:4000],
            "source_url": href,
            "discovery_score": score,
        })
        if len(results) >= limit:
            break
    return results


def discover_mostaql(*, url: str = BASE_URL, limit: int = 40, timeout: int = 20) -> list[dict[str, Any]]:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "KhyratMarketplaceDiscovery/1.0"})
    response.raise_for_status()
    return parse_projects(response.text, limit=limit)


def merge_discoveries(existing: list[dict[str, Any]], discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url = {str(item.get("source_url")): item for item in existing if item.get("source_url")}
    for item in discovered:
        key = str(item.get("source_url"))
        if key:
            by_url[key] = {**by_url.get(key, {}), **item}
    return sorted(by_url.values(), key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
