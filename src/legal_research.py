from __future__ import annotations
import html as html_lib, re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse
import requests

TIMEOUT=15
CURRENT_YEAR=datetime.now(timezone.utc).year
MAX_RESULTS=8
MAX_SOURCE_CHARS=18000
COURT=("cc.gov.eg","www.cc.gov.eg")
ADMIN=("esc.gov.eg","www.esc.gov.eg","stg.esc.gov.eg")
LAWS=("cc.gov.eg","www.cc.gov.eg","manshurat.org")

class _P(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag.lower() in {"script","style","noscript","svg"}: self.skip+=1
    def handle_endtag(self,tag):
        if tag.lower() in {"script","style","noscript","svg"} and self.skip: self.skip-=1
    def handle_data(self,data):
        if not self.skip and data.strip(): self.parts.append(data.strip())

def _clean(x): return re.sub(r"\s+"," ",str(x or "")).strip()
def _domain(u): return urlparse(u).netloc.lower().removeprefix("www.")
def _unwrap(u):
    q=parse_qs(urlparse(u).query).get("uddg",[""])[0]
    return unquote(q) if q else u

def _search(q):
    try:
        r=requests.get("https://html.duckduckgo.com/html/",params={"q":q,"kl":"eg-ar"},headers={"User-Agent":"Mozilla/5.0 Khyrat-Legal-Content-Engine/1.0"},timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        print(f"Legal research search unavailable: {q!r} :: {e}"); return []
    out=[]; seen=set()
    pat=re.compile(r'<a[^>]+class=["\\']result__a["\\'][^>]+href=["\\']([^"\\']+)["\\'][^>]*>(.*?)</a>',re.I|re.S)
    for m in pat.finditer(r.text):
        u=_unwrap(html_lib.unescape(m.group(1))); t=_clean(re.sub(r"<[^>]+>"," ",html_lib.unescape(m.group(2))))
        if not u.startswith("http") or not t or u in seen: continue
        seen.add(u); out.append({"url":u,"title":t})
        if len(out)>=MAX_RESULTS: break
    return out

def _fetch(u):
    try:
        r=requests.get(u,headers={"User-Agent":"Mozilla/5.0 Khyrat-Legal-Content-Engine/1.0"},timeout=TIMEOUT)
        r.raise_for_status(); p=_P(); p.feed(r.text); return _clean(" ".join(p.parts))[:MAX_SOURCE_CHARS]
    except Exception as e:
        print(f"Legal research source unavailable: {u} :: {e}"); return ""

def _case(t):
    for pat in [
        r"(?:الطعن|الطعن رقم)\s*(?:رقم\s*)?([٠-٩0-9]+\s+لسنة\s+[٠-٩0-9]+\s+ق(?:ضائية)?)",
        r"(?:الطعن|الطعن رقم)\s+رقم\s*([٠-٩0-9]+\s+لسنة\s+[٠-٩0-9]+\s+ق(?:ضائية)?)"]:
        m=re.search(pat,t,re.I)
        if m:return _clean(m.group(1))
    return ""
def _date(t):
    m=re.search(r"(?:جلسة|بتاريخ|تاريخ الجلسة)\s*([٠-٩0-9]{1,2}[./-][٠-٩0-9]{1,2}[./-][٠-٩0-9]{2,4})",t)
    return m.group(1) if m else ""
def _quote(t,topic,max_words=24):
    terms=[x for x in re.findall(r"[\u0600-\u06ff]{4,}",topic) if x not in {"قانون","مصر","الموضوع"}]
    ss=[s.strip() for s in re.split(r"(?<=[.!؟])\s+",t) if 8<=len(s.split())<=80]
    if not ss:return ""
    ss.sort(key=lambda s:sum(term in s for term in terms),reverse=True)
    return _clean(" ".join(ss[0].split()[:max_words]))
def _allowed(u):
    d=_domain(u); return d in COURT or d in ADMIN or d in LAWS

def research_legal_topic(topic, existing=""):
    topic=_clean(topic)
    if not topic:return _clean(existing)
    queries=[
        f'site:cc.gov.eg/principle "{topic}"',
        f'site:cc.gov.eg/principle {topic} "الطعن رقم" 2026',
        f'site:cc.gov.eg/principle {topic} "الطعن رقم" {CURRENT_YEAR - 1}',
        f'site:esc.gov.eg "{topic}" "الطعن رقم"',
        f'site:esc.gov.eg "{topic}" "المحكمة الإدارية العليا"',
        f'site:cc.gov.eg "أحدث التشريعات" {topic} 2026',
        f'site:manshurat.org {topic} قانون 2026',
        f'site:manshurat.org {topic} قانون {CURRENT_YEAR - 1}',
    ]
    cand=[]; seen=set()
    for q in queries:
        for x in _search(q):
            if x["url"] in seen or not _allowed(x["url"]): continue
            seen.add(x["url"]); cand.append(x)
    records=[]
    for x in cand[:MAX_RESULTS]:
        body=_fetch(x["url"])
        if not body: continue
        d=_domain(x["url"]); court="محكمة النقض" if d in COURT else ("المحكمة الإدارية العليا" if d in ADMIN else "")
        case=_case(body)
        if case and court:
            records.append(("judgment_or_principle",court,case,_date(body),x["title"],_quote(body,topic),x["url"]))
        elif d in LAWS:
            records.append(("current_legislation_source","تشريع","",_date(body),x["title"],"",x["url"]))
    lines=[
        "LEGAL RESEARCH PACKET — VERIFIED WEB SOURCES ONLY",
        f"Research date: {datetime.now(timezone.utc).date().isoformat()}",
        f"Topic: {topic}",
        "",
        "WRITER RULES:",
        "- Prefer the newest effective legislation; check publication and commencement dates.",
        "- If an amendment replaced an older rule, use the current effective rule and explain the change when material.",
        "- Quote only text actually retrieved from a source, max 24 words per source.",
        "- Every judicial quotation must include the verified court and exact case number.",
        "- Never invent a case number, date, quotation, statute number, or legal rule.",
        "- If no relevant verified judgment exists, omit the judicial quotation and use a verified general principle or current legislation instead.",
        ""
    ]
    if not records: lines.append("No sufficiently verified topic-specific court/legislation source was retrieved automatically.")
    for i,(typ,court,case,date,title,quote,url) in enumerate(records[:6],1):
        lines += [f"SOURCE {i}",f"Type: {typ}",f"Court/source: {court}",f"Case number: {case or 'N/A'}",f"Date: {date or 'not stated'}",f"Title: {title}",f"Verified short quotation: {quote or 'N/A'}",f"URL: {url}",""]
    if existing: lines += ["EXISTING SHEET LEGAL SOURCES:",_clean(existing)[:8000]]
    return "\n".join(lines)
