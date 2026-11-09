from __future__ import annotations
import html as html_lib, re, io
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
LAWS=("cc.gov.eg","www.cc.gov.eg","manshurat.org","fra.gov.eg")

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
    pat=re.compile(r"<a[^>]+class=['\"]result__a['\"][^>]+href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>",re.I|re.S)
    for m in pat.finditer(r.text):
        u=_unwrap(html_lib.unescape(m.group(1))); t=_clean(re.sub(r"<[^>]+>"," ",html_lib.unescape(m.group(2))))
        if not u.startswith("http") or not t or u in seen: continue
        seen.add(u); out.append({"url":u,"title":t})
        if len(out)>=MAX_RESULTS: break
    return out

def _fetch(u):
    try:
        r=requests.get(u,headers={"User-Agent":"Mozilla/5.0 Khyrat-Legal-Content-Engine/1.0"},timeout=TIMEOUT)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "").lower()
        if "pdf" in content_type or urlparse(u).path.lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(r.content))
                return _clean(" ".join(page.extract_text() or "" for page in reader.pages))[:MAX_SOURCE_CHARS]
            except Exception as pdf_exc:
                print(f"Legal PDF text extraction unavailable: {u} :: {pdf_exc}")
                return ""
        p=_P(); p.feed(r.text); return _clean(" ".join(p.parts))[:MAX_SOURCE_CHARS]
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
def _effective(t):
    patterns = [
        r"(?:يعمل به|تاريخ العمل به|بدء العمل به)\s*(?:من|اعتبارًا من|اعتبارا من)?\s*([^،.;]{4,80})",
        r"(?:صدر|صدرت)\s+[^.]{0,80}\s+(?:في|بتاريخ)\s*([٠-٩0-9]{1,2}[./-][٠-٩0-9]{1,2}[./-][٠-٩0-9]{2,4})",
    ]
    for pattern in patterns:
        m=re.search(pattern,t,re.I)
        if m:
            return _clean(m.group(1))
    return ""

def _quote(t,topic,max_words=24):
    terms=[x for x in re.findall(r"[\u0600-\u06ff]{4,}",topic) if x not in {"قانون","مصر","الموضوع"}]
    # Short, complete sentences can still be meaningful source quotations.
    ss=[s.strip() for s in re.split(r"(?<=[.!؟])\s+",t) if 5<=len(s.split())<=80]
    if not ss:return ""
    ss.sort(key=lambda s:sum(term in s for term in terms),reverse=True)
    return _clean(" ".join(ss[0].split()[:max_words]))
def _allowed(u):
    d=_domain(u); return d in COURT or d in ADMIN or d in LAWS



def _norm_legal_text(value: str) -> str:
    value = str(value or "").casefold()
    value = re.sub(r"[إأآٱ]", "ا", value).replace("ى", "ي")
    value = re.sub(r"[٠-٩]", lambda m: str("٠١٢٣٤٥٦٧٨٩".index(m.group(0))), value)
    value = re.sub(r"[\u064B-\u065F\u0670ـ]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_precise_legal_claims(text: str) -> list[str]:
    """Return precise legal references that must be supported by retrieved source text."""
    value = str(text or "")
    claims: list[str] = []
    patterns = [
        r"قانون\s+(?:رقم\s*)?[٠-٩0-9]+\s+لسنة\s+[٠-٩0-9]+",
        r"المادة\s*(?:رقم\s*)?[（(]?\s*(?:[٠-٩0-9]+|الأولى|الاولى|الثانية|الثانيه|الثالثة|الثالثه|الرابعة|الرابعه|الخامسة|الخامسه|السادسة|السادسه|السابعة|السابعه|الثامنة|الثامنه|التاسعة|التاسعه|العاشرة|العاشره)\s*[）)]?(?:\s+من\s+قانون\s+(?:رقم\s*)?[٠-٩0-9]+\s+لسنة\s+[٠-٩0-9]+)?",
        r"(?:الطعن|الطعن رقم)\s*(?:رقم\s*)?[٠-٩0-9]+\s+لسنة\s+[٠-٩0-9]+\s+ق(?:ضائية)?",
        r"جلسة\s*[٠-٩0-9]{1,2}[./-][٠-٩0-9]{1,2}[./-][٠-٩0-9]{2,4}",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, value, flags=re.I):
            claim = _clean(match.group(0))
            if claim and claim not in claims:
                claims.append(claim)
    return claims


def validate_legal_citations(text: str, research_packet: str) -> list[str]:
    """Block unsupported or fabricated precise citations before social publication."""
    value = str(text or "")
    normalized_post = _norm_legal_text(value)
    # Spreadsheet/user-supplied notes are leads, not verification evidence.
    verified_packet = str(research_packet or "").split("EXISTING SHEET LEGAL SOURCES:", 1)[0]
    normalized_evidence = _norm_legal_text(verified_packet)

    issues: list[str] = []
    if "قانون الادارة العامة" in normalized_post:
        issues.append("اسم تشريع غير موثق/مريب: قانون الإدارة العامة؛ احذف الإسناد أو استبدله بنص مصري محدد تم التحقق منه.")

    for claim in extract_precise_legal_claims(value):
        if _norm_legal_text(claim) not in normalized_evidence:
            issues.append(f"إحالة قانونية دقيقة لم تظهر حرفيًا في أدلة المصادر المسترجعة: {claim}")
    return list(dict.fromkeys(issues))



def research_legal_topic(topic, existing=""):
    topic=_clean(topic)
    if not topic:return _clean(existing)
    queries=[
        f'site:cc.gov.eg/principle "{topic}"',
        f'site:cc.gov.eg/principle {topic} "الطعن رقم" {CURRENT_YEAR}',
        f'site:cc.gov.eg/principle {topic} "الطعن رقم" {CURRENT_YEAR - 1}',
        f'site:esc.gov.eg "{topic}" "الطعن رقم"',
        f'site:esc.gov.eg "{topic}" "المحكمة الإدارية العليا"',
        f'site:cc.gov.eg "أحدث التشريعات" {topic} {CURRENT_YEAR}',
        f'site:manshurat.org {topic} قانون {CURRENT_YEAR}',
        f'site:manshurat.org {topic} قانون {CURRENT_YEAR - 1}',
    ]
    # Law 175/2018 is frequently cited in cybercrime content. Retrieve its
    # official FRA-hosted PDF directly so exact statutory references can be
    # checked against primary government text rather than user notes.
    topic_norm = _norm_legal_text(topic)
    cybercrime_topic = any(term in topic_norm for term in ("جرائم الكترونيه", "جرائم تقنيه المعلومات", "الابتزاز الالكتروني", "الجرائم المعلوماتيه"))
    if cybercrime_topic:
        queries.append('site:fra.gov.eg "قانون رقم 175 لسنة 2018"')
    cand=[]; seen=set()
    if cybercrime_topic:
        official_law_pdf = "https://fra.gov.eg/wp-content/uploads/2025/01/%D9%82%D8%A7%D9%86%D9%88%D9%86-%D8%B1%D9%82%D9%85-175-%D9%84%D8%B3%D9%86%D8%A9-2018-%D8%A8%D8%AA%D8%A7%D8%B1%D9%8A%D8%AE-2018-08-14.pdf"
        cand.append({"url": official_law_pdf, "title": "القانون رقم 175 لسنة 2018 — النسخة المنشورة على موقع الهيئة العامة للرقابة المالية"})
        seen.add(official_law_pdf)
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
            records.append(("judgment_or_principle",court,case,_date(body),_effective(body),x["title"],_quote(body,topic),x["url"],body[:3000]))
        elif d in LAWS:
            records.append(("current_legislation_source","تشريع","",_date(body),_effective(body),x["title"],"",x["url"],body[:3000]))
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
    for i,(typ,court,case,date,effective,title,quote,url,evidence) in enumerate(records[:6],1):
        lines += [f"SOURCE {i}",f"Type: {typ}",f"Court/source: {court}",f"Case number: {case or 'N/A'}",f"Date: {date or 'not stated'}",f"Effective/publication detail: {effective or 'not stated'}",f"Title: {title}",f"Verified short quotation: {quote or 'N/A'}",f"VERIFIED SOURCE TEXT (retrieved): {evidence}",f"URL: {url}",""]
    if existing: lines += ["EXISTING SHEET LEGAL SOURCES:",_clean(existing)[:8000]]
    return "\n".join(lines)
