"""Public-web discovery of Egyptian B2B legal-service decision makers.

No authenticated LinkedIn scraping is used. Public search results are normalized
into a lead file, scored for legal-service buying power, and deduplicated by URL.
"""
from __future__ import annotations

import csv
import html
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests

DATA_DIR = Path("marketplace_data")
LEADS_JSON = DATA_DIR / "legal_decision_makers.json"
LEADS_CSV = DATA_DIR / "legal_decision_makers.csv"
DEFAULT_COUNTRY = "Egypt"
DEFAULT_LIMIT = 100

DECISION_ROLES = {
    "Founder": 100, "Co-Founder": 100, "Owner": 98, "CEO": 98,
    "Chief Executive Officer": 98, "Managing Director": 96, "General Manager": 90,
    "Chairman": 88, "Partner": 88, "COO": 84, "Chief Operating Officer": 84,
    "CFO": 82, "Chief Financial Officer": 82, "Head of HR": 80,
    "HR Director": 80, "Human Resources Director": 80, "HR Manager": 74,
    "Legal Director": 96, "Legal Manager": 94, "Head of Legal": 96,
    "General Counsel": 98, "Corporate Affairs Director": 90,
    "Procurement Manager": 68, "Procurement Director": 74,
}
ROLE_ALIASES = {
    "chief executive officer": "CEO", "chief operating officer": "COO",
    "chief financial officer": "CFO", "co-founder": "Co-Founder",
    "managing director": "Managing Director", "general manager": "General Manager",
    "general counsel": "General Counsel", "head of legal": "Head of Legal",
    "legal director": "Legal Director", "legal manager": "Legal Manager",
    "hr director": "HR Director", "human resources director": "HR Director",
    "hr manager": "HR Manager", "head of hr": "Head of HR",
}
SERVICE_FIT = {
    "Founder": ("عقود الشركات، تأسيس الشركات، الاستشارات المستمرة", 18),
    "Co-Founder": ("عقود الشركات، تأسيس الشركات، الاستشارات المستمرة", 18),
    "Owner": ("العقود، قانون العمل، المستشار القانوني الخارجي", 18),
    "CEO": ("العقود، الحوكمة، المستشار القانوني الخارجي", 18),
    "Managing Director": ("العقود، التشغيل، المستشار القانوني الخارجي", 17),
    "General Manager": ("العقود، التشغيل، قانون العمل", 15),
    "Chairman": ("الحوكمة، الشركات، العقود", 14),
    "Partner": ("العقود، الشركات، التفاوض", 15),
    "COO": ("العقود التشغيلية، الموردين، الامتثال", 14),
    "CFO": ("العقود التجارية، الامتثال، المخاطر", 13),
    "Head of HR": ("قانون العمل، لوائح الموارد البشرية، التحقيقات", 17),
    "HR Director": ("قانون العمل، لوائح الموارد البشرية، التحقيقات", 17),
    "HR Manager": ("قانون العمل، عقود العمل، السياسات", 15),
    "Legal Director": ("دعم قانوني متخصص، العقود، التفاوض", 16),
    "Legal Manager": ("العقود، المراجعة القانونية، النزاعات", 16),
    "Head of Legal": ("العقود، المراجعة القانونية، التفاوض", 16),
    "General Counsel": ("الدعم القانوني المؤسسي، العقود، الحوكمة", 18),
    "Corporate Affairs Director": ("الشركات، الامتثال، الحوكمة", 15),
    "Procurement Manager": ("عقود الموردين، الشروط التجارية، التفاوض", 11),
    "Procurement Director": ("عقود الموردين، التفاوض، إدارة المخاطر", 12),
}

@dataclass
class Lead:
    name: str
    title: str
    normalized_role: str
    company: str
    linkedin_url: str
    location: str = "Egypt"
    industry: str = ""
    company_size: str = ""
    company_url: str = ""
    public_email: str = ""
    public_phone: str = ""
    legal_need: str = ""
    score: int = 0
    source: str = "public_search"
    evidence: str = ""
    status: str = "READY"


def _clean(value: str) -> str:
    value = html.unescape(unquote(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def linkedin_profile(url: str) -> str:
    try:
        p = urlparse(url)
    except ValueError:
        return ""
    if (p.hostname or "").lower().replace("www.", "") != "linkedin.com":
        return ""
    path = p.path.rstrip("/")
    if not re.match(r"^/in/[A-Za-z0-9_%.-]+$", path, re.I):
        return ""
    return f"https://www.linkedin.com{path}"


def normalize_role(title: str) -> tuple[str, int]:
    text = _clean(title).lower()
    best_role, best_weight = "", 0
    for role, weight in DECISION_ROLES.items():
        if role.lower() in text and weight > best_weight:
            best_role = ROLE_ALIASES.get(role.lower(), role)
            best_weight = weight
    return best_role, best_weight


def _unwrap_search_url(url: str) -> str:
    url = html.unescape(url)
    try:
        q = parse_qs(urlparse(url).query)
        return q.get("uddg", [url])[0]
    except Exception:
        return url


def _search_duckduckgo(query: str, timeout: int = 15) -> list[tuple[str, str, str]]:
    try:
        r = requests.get("https://html.duckduckgo.com/html/?q=" + quote(query), timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 KhyratLeadDiscovery/1.0"})
        if not r.ok:
            return []
        body = r.text
    except requests.RequestException:
        return []
    links = re.findall(r'<a[^>]+class=["\']result__a["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', body, re.I | re.S)
    snippets = re.findall(r'<a[^>]+class=["\']result__snippet["\'][^>]*>(.*?)</a>', body, re.I | re.S)
    return [(_unwrap_search_url(u), _clean(t), _clean(snippets[i]) if i < len(snippets) else "")
            for i, (u, t) in enumerate(links)]


def _search_bing(query: str, timeout: int = 15) -> list[tuple[str, str, str]]:
    try:
        r = requests.get("https://www.bing.com/search?q=" + quote(query), timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 KhyratLeadDiscovery/1.0"})
        if not r.ok:
            return []
        body = r.text
    except requests.RequestException:
        return []
    out = []
    for block in re.findall(r'<li class="b_algo".*?</li>', body, re.I | re.S):
        m = re.search(r'<h2><a href="([^"]+)"[^>]*>(.*?)</a>', block, re.I | re.S)
        if not m:
            continue
        s = re.search(r'<p>(.*?)</p>', block, re.I | re.S)
        out.append((_unwrap_search_url(m.group(1)), _clean(m.group(2)), _clean(s.group(1) if s else "")))
    return out


def search(query: str, timeout: int = 15) -> list[tuple[str, str, str]]:
    provider = os.getenv("LEGAL_LEAD_SEARCH_PROVIDER", "auto").lower()
    if provider == "bing":
        return _search_bing(query, timeout)
    if provider == "duckduckgo":
        return _search_duckduckgo(query, timeout)
    return _search_duckduckgo(query, timeout) or _search_bing(query, timeout)


def parse_result(url: str, title: str, snippet: str, fallback_role: str) -> Lead | None:
    linkedin = linkedin_profile(url)
    if not linkedin:
        return None
    combined = _clean(f"{title} {snippet}")
    role, weight = normalize_role(combined)
    role = role or fallback_role
    weight = weight or DECISION_ROLES.get(fallback_role, 50)
    title_clean = _clean(title)
    parts = [p.strip() for p in re.split(r"\s+[-|–—]\s+", title_clean) if p.strip()]
    name = parts[0] if parts else ""
    if name.lower() in {"linkedin", "linkedin login", "sign in"} or len(name) < 3:
        return None
    company = parts[2] if len(parts) >= 3 else (parts[1] if len(parts) == 2 and role.lower() not in parts[1].lower() else "")
    legal_need, fit_bonus = SERVICE_FIT.get(role, ("الخدمات القانونية للشركات", 8))
    score = min(100, 40 + weight // 3 + fit_bonus)
    return Lead(name=name[:120], title=title_clean[:180], normalized_role=role, company=company[:160],
                linkedin_url=linkedin, legal_need=legal_need, score=score, evidence=_clean(snippet)[:500])


def query_set(country: str = DEFAULT_COUNTRY, industries: list[str] | None = None) -> list[tuple[str, str]]:
    roles = ["Founder", "CEO", "Managing Director", "Owner", "General Manager", "HR Director",
             "HR Manager", "Head of Legal", "Legal Manager", "CFO"]
    industries = industries or ["manufacturing", "technology", "healthcare", "construction", "trading",
                                "logistics", "real estate", "food", "services"]
    return [(f'site:linkedin.com/in/ "{role}" "{industry}" "{country}"', role)
            for role in roles for industry in industries]


def discover_leads(*, limit: int = DEFAULT_LIMIT, country: str = DEFAULT_COUNTRY,
                   industries: list[str] | None = None, timeout: int = 15) -> list[dict]:
    by_url: dict[str, Lead] = {}
    for query, fallback_role in query_set(country, industries):
        for url, title, snippet in search(query, timeout):
            lead = parse_result(url, title, snippet, fallback_role)
            if not lead:
                continue
            lead.location = country
            lead.industry = next((x for x in (industries or []) if x.lower() in (title + " " + snippet).lower()), "")
            old = by_url.get(lead.linkedin_url)
            if old is None or lead.score > old.score:
                by_url[lead.linkedin_url] = lead
            if len(by_url) >= limit * 2:
                break
        if len(by_url) >= limit * 2:
            break
    return [asdict(x) for x in sorted(by_url.values(), key=lambda x: (-x.score, x.company, x.name))[:limit]]


def merge_leads(existing: list[dict], discovered: list[dict]) -> list[dict]:
    by_url = {str(x.get("linkedin_url")): x for x in existing if x.get("linkedin_url")}
    for item in discovered:
        url = str(item.get("linkedin_url", ""))
        if url:
            previous = by_url.get(url, {})
            by_url[url] = {**previous, **item, "status": previous.get("status", item.get("status", "READY"))}
    return sorted(by_url.values(), key=lambda x: (-int(x.get("score", 0)), str(x.get("company", "")), str(x.get("name", ""))))


def save_leads(leads: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LEADS_JSON.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = list(Lead.__annotations__.keys())
    with LEADS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(leads)


def load_leads() -> list[dict]:
    if not LEADS_JSON.exists():
        return []
    try:
        value = json.loads(LEADS_JSON.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


if __name__ == "__main__":
    discovered = discover_leads(limit=int(os.getenv("LEGAL_LEAD_LIMIT", "100")))
    merged = merge_leads(load_leads(), discovered)
    save_leads(merged)
    print(json.dumps({"discovered": len(discovered), "total": len(merged), "json": str(LEADS_JSON), "csv": str(LEADS_CSV)}, ensure_ascii=False))
