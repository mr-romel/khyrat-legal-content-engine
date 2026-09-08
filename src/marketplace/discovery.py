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
    "كتابة قانونية", "بحث قانوني", "شروط وأحكام", "سياسة الخصوصية", "امتثال", "حوكمة",
)
ROLE_NOISE = (
    "محاسب", "محاسبة", "مدير مالي", "مبيعات", "مسوق", "تسويق", "كوتش", "coach",
    "موظف", "مسؤول", "مندوب", "تطوير الأعمال", "دراسة جدوى", "تسعير منتجات", "إدارة حسابات",
)
DETAIL_HEADINGS = ("تفاصيل المشروع", "وصف المشروع", "المطلوب", "تفاصيل الطلب")
STOP_HEADINGS = (
    "المهارات المطلوبة", "المهارات", "الميزانية", "مدة التنفيذ", "مدة المشروع", "عدد العروض",
    "العروض", "الأسئلة", "الأسئلة الشائعة", "عن صاحب المشروع", "مشاريع أخرى", "تسجيل الدخول", "إنشاء حساب",
)
ERROR_MARKERS = (
    "403 forbidden", "401 unauthorized", "404 not found", "429 too many requests", "access denied",
    "request blocked", "captcha", "cloudflare", "service unavailable",
)


def _clean(value: str) -> str:
    value = unquote(unescape(value).replace("\\/", "/"))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    return re.sub(r"\s+", " ", value).strip()


def _legal_score(title: str, description: str) -> int:
    t, b = _clean(title).lower(), _clean(description).lower()
    ts = sum(x in t for x in STRONG_TERMS)
    tn = sum(x in t for x in LEGAL_TERMS)
    bs = sum(x in b for x in STRONG_TERMS)
    bn = sum(x in b for x in LEGAL_TERMS)
    if ts == 0 and tn == 0 and bs == 0:
        return 0
    score = 20 + ts * 20 + tn * 8 + bs * 10 + bn * 3
    if ts:
        score += 25
    return min(100, score)


def _is_relevant_opportunity(title: str, description: str) -> bool:
    """Accept legal-service intent, not merely generic business/legal-adjacent wording."""
    t, b = _clean(title).lower(), _clean(description).lower()
    if not t:
        return False
    if any(x in t for x in ROLE_NOISE) and not any(x in t for x in STRONG_TERMS):
        return False
    title_strong = sum(x in t for x in STRONG_TERMS)
    body_strong = sum(x in b for x in STRONG_TERMS)
    return title_strong > 0 or body_strong >= 2


def _canonical_url(href: str) -> str:
    href = urljoin(BASE_URL, unescape(href).replace("\\/", "/").strip())
    p = urlsplit(href)
    if (p.hostname or "").lower() not in {"mostaql.com", "www.mostaql.com"}:
        return ""
    return f"https://mostaql.com{p.path.rstrip('/')}"


def _is_project_url(href: str) -> bool:
    path = urlsplit(href).path.rstrip("/")
    return path != "/project/create" and bool(re.fullmatch(r"/project/[^/?#\s<>\"']+", path, re.I))


def _add(results: list[dict[str, Any]], seen: set[str], href: str, title: str, description: str,
         limit: int, *, official: bool = False) -> None:
    href = _canonical_url(href)
    if len(results) >= limit or not href or href in seen or not _is_project_url(href):
        return
    title, description = _clean(title)[:180], _clean(description)[:4000]
    if len(title) < 4:
        title = _clean(href.rsplit("/", 1)[-1].replace("-", " "))
    score = _legal_score(title, description)
    if not official and (score < 24 or not _is_relevant_opportunity(title, description)):
        return
    seen.add(href)
    candidate_score = max(score, 60) if official else (score if score >= 24 else 1)
    results.append({"platform": "mostaql", "title": title, "description": description or title,
                    "source_url": href, "discovery_score": candidate_score})


def parse_projects(text: str, limit: int = 40, *, official: bool = False) -> list[dict[str, Any]]:
    text = unescape(text).replace("\\/", "/")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    anchor = re.compile(r'<a\b[^>]*?href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<body>.*?)</a>', re.I | re.S)
    urls = re.compile(r'(?P<href>(?:https?://(?:www\.)?mostaql\.com)?/project/[^/?#\s<>"\']+)', re.I)
    for m in anchor.finditer(text):
        href = _canonical_url(m.group("href"))
        if _is_project_url(href):
            body = _clean(m.group("body"))
            _add(results, seen, href, body, body, limit, official=official)
            if len(results) >= limit: return results
    for m in urls.finditer(text):
        href = _canonical_url(m.group("href"))
        if _is_project_url(href):
            slug = _clean(href.rsplit("/", 1)[-1].replace("-", " "))
            _add(results, seen, href, slug, slug, limit, official=official)
            if len(results) >= limit: return results
    return results


def _reader_url(target: str) -> str:
    return "https://r.jina.ai/https://" + target.removeprefix("https://").removeprefix("http://")


def _translate_url(target: str) -> str:
    p = urlsplit(target)
    path, query = quote(p.path, safe="/:"), quote(p.query, safe="=&%")
    suffix = f"?{query}&" if query else "?"
    return f"https://mostaql-com.translate.goog{path}{suffix}_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en"


def _agentsweb_url(target: str) -> str:
    return "https://agentsweb.org/fetch?url=" + quote(target, safe="")


def _looks_like_error_page(body: str) -> bool:
    if not body: return True
    text = _clean(body[:12000]).lower()
    return any(x in text for x in ERROR_MARKERS)


def _get(url: str, timeout: int) -> str:
    try:
        r = requests.get(url, timeout=min(timeout, 15), headers={"User-Agent": "Mozilla/5.0 (compatible; KhyratMarketplaceDiscovery/26.0)"})
        if not r.ok or _looks_like_error_page(r.text): return ""
        return r.text
    except requests.RequestException:
        return ""


def _looks_like_business_response(body: str) -> bool:
    return bool(body and len(body) >= 300 and ("mostaql" in body.lower() or "مستقل" in body.lower()) and
                re.search(r"/project/[^/?#\s<>\"']+", body, re.I))


def _fetch_business_page(timeout: int) -> str:
    for target in (BASE_URL, BASE_URL + "?sort=latest", BASE_URL + "?page=1"):
        for transport in (target, _reader_url(target), _translate_url(target), _agentsweb_url(target)):
            body = _get(transport, timeout)
            if _looks_like_business_response(body) and parse_projects(body, 1, official=True):
                return body
    return ""


def _fetch_project_page(url: str, timeout: int) -> str:
    for transport in (_reader_url(url), _translate_url(url), _agentsweb_url(url)):
        body = _get(transport, timeout)
        if body and not _looks_like_error_page(body) and ("mostaql" in body.lower() or "مستقل" in body.lower()):
            return body
    return ""


def _project_is_open_text(text: str) -> bool:
    n = _clean(text).lower()
    if not n or _looks_like_error_page(n): return False
    return not any(x in n for x in ("المشروع مغلق", "المشروع منتهي", "تم إغلاق المشروع", "تم التوظيف", "closed", "expired", "archived"))


def _project_is_open(url: str, page: str | None = None, timeout: int = 8) -> bool:
    body = page if page is not None else _fetch_project_page(url, timeout)
    return bool(body) and _project_is_open_text(body)


def validate_live_projects(projects: list[dict[str, Any]], *, limit: int = 10, timeout: int = 8) -> list[dict[str, Any]]:
    valid = []
    for item in projects:
        if len(valid) >= limit: break
        if _project_is_open(str(item.get("source_url", "")), timeout=timeout):
            valid.append({**item, "live": True})
    return valid


def _is_noise_title(title: str) -> bool:
    n = _clean(title).lower()
    return len(n) < 4 or any(x in n for x in ("var ishomepage", "var isorganizationpage", "403 forbidden", "404 not found", "401 unauthorized", "mostaql", "مستقل", "تسجيل الدخول", "إنشاء حساب", "access denied"))


def _extract_project_content(page: str, fallback_title: str) -> tuple[str, str]:
    raw = unescape(page).replace("\\/", "/")
    lines = [_clean(x) for x in raw.splitlines() if _clean(x)]
    title = _clean(fallback_title)[:180]
    for line in lines[:120]:
        heading = re.sub(r"^#{1,6}\s*", "", line).strip()
        if heading.startswith("#") or _is_noise_title(heading):
            continue
        if len(heading) <= 180 and _legal_score(heading, "") >= 45 and heading != title:
            if re.match(r"^(?:مشروع|مطلوب|طلب|خبير|مستشار|مراجعة|صياغة|استشارة|محامي|خدمة)", heading):
                title = heading
                break
    details = {x.rstrip(":").strip().lower() for x in DETAIL_HEADINGS}
    stops = {x.rstrip(":").strip().lower() for x in STOP_HEADINGS}
    start = next((i + 1 for i, line in enumerate(lines) if line.rstrip(":").strip().lower() in details), None)
    if start is None:
        start = 0
    body = []
    for line in lines[start:]:
        n = line.rstrip(":").strip().lower()
        if n in stops: break
        if _is_noise_title(line) or re.fullmatch(r"[-*_]{3,}", line): continue
        if line.startswith(("var ", "const ", "let ", "function ")): continue
        body.append(line)
        if sum(map(len, body)) >= 5000: break
    return title, _clean(" ".join(body))[:4000]


def discover_mostaql(*, url: str = BASE_URL, limit: int = 10, timeout: int = 20) -> list[dict[str, Any]]:
    _ = url
    raw = _fetch_business_page(timeout)
    candidates = parse_projects(raw, limit=max(limit * 20, 200), official=True) if raw else []
    if not candidates: return []
    def inspect(item: dict[str, Any]) -> dict[str, Any] | None:
        page = _fetch_project_page(str(item["source_url"]), min(timeout, 8))
        if not page or not _project_is_open(str(item["source_url"]), page): return None
        title, description = _extract_project_content(page, item.get("title", ""))
        if not _is_relevant_opportunity(title, description): return None
        score = _legal_score(title, description)
        if score < 24: return None
        return {**item, "title": _clean(title)[:180], "description": description or _clean(title),
                "discovery_score": score, "live": True, "source_filter": BUSINESS_FILTER_URL,
                "source_kind": "mostaql_business_filter"}
    scored = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(inspect, item) for item in candidates]
        for future in as_completed(futures):
            item = future.result()
            if item: scored.append(item)
    return sorted(scored, key=lambda x: int(x.get("discovery_score", 0)), reverse=True)[:limit]


def merge_discoveries(existing: list[dict[str, Any]], discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = {str(x.get("source_url")) for x in discovered if x.get("source_url")}
    by_url = {
        str(x.get("source_url")): x for x in existing
        if x.get("source_url") and not (
            x.get("source_kind") == "mostaql_business_filter" and str(x.get("source_url")) not in current
        )
    }
    for item in discovered:
        key = str(item.get("source_url"))
        if key: by_url[key] = {**by_url.get(key, {}), **item}
    return sorted(by_url.values(), key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
