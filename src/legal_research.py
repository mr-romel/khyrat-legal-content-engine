from __future__ import annotations
import html as html_lib, re, io
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse
import requests

TIMEOUT=15
CURRENT_YEAR=datetime.now(timezone.utc).year
MAX_RESULTS=8
MAX_SOURCE_CHARS=250000
COURT=("cc.gov.eg","www.cc.gov.eg")
ADMIN=("esc.gov.eg","www.esc.gov.eg","stg.esc.gov.eg")
OFFICIAL_LAWS=("fra.gov.eg","mof.gov.eg","elpai.idsc.gov.eg","gafi.gov.eg","eta.gov.eg","nosi.gov.eg","moi.gov.eg","cabinet.gov.eg","presidency.eg","moj.gov.eg","labour.gov.eg","sis.gov.eg","caoa.gov.eg")
SECONDARY_LAWS=("manshurat.org","www.manshurat.org")
LAWS=tuple(set(OFFICIAL_LAWS+SECONDARY_LAWS))

class _P(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag.lower() in {"script","style","noscript","svg"}: self.skip+=1
    def handle_endtag(self,tag):
        if tag.lower() in {"script","style","noscript","svg"} and self.skip: self.skip-=1
    def handle_data(self,data):
        if not self.skip and data.strip(): self.parts.append(data.strip())

def _clean(x): return re.sub(r"\s+"," ",str(x or "")).strip()
def _domain(u):
    return (urlparse(str(u or "")).hostname or "").lower().rstrip(".").removeprefix("www.")


def _host_matches(host, roots):
    host = str(host or "").lower().rstrip(".").removeprefix("www.")
    return any(host == root or host.endswith("." + root) for root in roots)
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


def _source_evidence(text: str, topic: str) -> str:
    """Keep topic-relevant statutory passages, not merely the first pages of a long PDF."""
    value = _clean(text)
    normalized_topic = _norm_legal_text(topic)
    employment = any(term in normalized_topic for term in ("عمال", "عامل", "العمل", "العماله", "التشغيل", "ترخيص المهنه", "ترخيص العماله"))
    public_service = any(term in normalized_topic for term in ("وظيف", "تعيين", "الخدمه المدنيه", "الخدمة المدنية", "موظف"))
    impersonation = any(term in normalized_topic for term in ("انتحال", "حساب مزيف", "هويه مزيفه", "هوية مزيفة", "اسم كاذب"))
    if employment:
        patterns = [
            r"(?:المادة\s+السادسة|مادة\s*\(?\s*(?:السادسة|6|٦)\s*\)?)[^:]{0,20}:?.{0,1400}",
            r"مادة\s*\(?\s*(?:27|٢٧)\s*\)?\s*:?.{0,1600}",
            r"مادة\s*\(?\s*(?:33|٣٣|34|٣٤|40|٤٠|41|٤١|42|٤٢|43|٤٣|291|٢٩١)\s*\)?\s*:?.{0,1600}",
        ]
    elif public_service:
        patterns = [r"مادة\s*\(?\s*(?:4|٤|12|١٢|13|١٣|14|١٤|15|١٥|16|١٦|17|١٧)\s*\)?\s*:?.{0,1800}"]
    elif impersonation:
        patterns = [r"مادة\s*\(?\s*(?:24|٢٤|155|١٥٥|156|١٥٦|157|١٥٧|336|٣٣٦)\s*\)?\s*:?.{0,1800}"]
    if employment or public_service or impersonation:
        excerpts = []
        for pattern in patterns:
            for match in re.finditer(pattern, value, re.I):
                snippet = _clean(match.group(0))
                if snippet and snippet not in excerpts:
                    excerpts.append(snippet)
        if excerpts:
            # Preserve the exact law/year identifier even when the useful article
            # appears much later in a PDF and the header is outside the excerpt.
            law_refs = []
            law_pattern = r"(?:قانون|القانون)[^،؛.]{0,45}?(?:رقم\s*)?([٠-٩0-9]+)\s+لسنة\s+([٠-٩0-9]+)"
            for match in re.finditer(law_pattern, value, re.I):
                reference = f"قانون رقم {match.group(1)} لسنة {match.group(2)}"
                if reference not in law_refs:
                    law_refs.append(reference)
            return _clean(" ".join(law_refs + excerpts))[:9000]
    return value[:5000]

def _quote(t,topic,max_words=24):
    terms=[x for x in re.findall(r"[\u0600-\u06ff]{4,}",topic) if x not in {"قانون","مصر","الموضوع"}]
    # Short, complete sentences can still be meaningful source quotations.
    ss=[s.strip() for s in re.split(r"(?<=[.!؟])\s+",t) if 5<=len(s.split())<=80]
    if not ss:return ""
    ss.sort(key=lambda s:sum(term in s for term in terms),reverse=True)
    return _clean(" ".join(ss[0].split()[:max_words]))
def _allowed(u):
    parsed=urlparse(str(u or ""))
    d=_domain(u)
    return parsed.scheme == "https" and bool(parsed.hostname) and (_host_matches(d, COURT) or _host_matches(d, ADMIN) or _host_matches(d, LAWS))



def _norm_legal_text(value: str) -> str:
    value = str(value or "").casefold()
    value = re.sub(r"[إأآٱ]", "ا", value).replace("ى", "ي")
    # Definite-article form used in official statute headings is equivalent
    # to the common citation form used in social copy.
    value = value.replace("القانون رقم", "قانون رقم")
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



def has_verified_legal_source(packet: str) -> bool:
    """True only when the research packet contains at least one whitelisted HTTPS source."""
    text = str(packet or "")
    blocks = re.split(r"(?m)^SOURCE\s+\d+\s*$", text)
    for block in blocks[1:]:
        match = re.search(r"(?m)^URL:\s*(https://\S+)", block)
        evidence = re.search(r"(?m)^VERIFIED SOURCE TEXT \(retrieved\):\s*(.{30,})$", block)
        title = re.search(r"(?m)^Title:\s*\S", block)
        if match and evidence and title and _allowed(match.group(1).rstrip(").,;")):
            return True
    return False


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
        f'site:labour.gov.eg {topic} قانون العمل',
        f'site:sis.gov.eg قانون العمل 14 لسنة 2025',
        f'site:nosi.gov.eg {topic} قانون الخدمة المدنية 81 لسنة 2016',
        f'site:caoa.gov.eg {topic} قانون الخدمة المدنية اللائحة التنفيذية',
        f'site:fra.gov.eg {topic} قانون 175 لسنة 2018 انتحال الشخصية',
        f'site:manshurat.org {topic} قانون العقوبات انتحال الشخصية',
        f'site:elpai.idsc.gov.eg {topic} قانون {CURRENT_YEAR}',
        f'site:mof.gov.eg {topic} تشريع {CURRENT_YEAR}',
        f'site:gafi.gov.eg {topic} قانون قرار {CURRENT_YEAR}',
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
    employment_topic = any(term in topic_norm for term in ("عمال", "عامل", "العمل", "العماله", "التشغيل", "ترخيص المهنه", "ترخيص العماله"))
    public_service_topic = any(term in topic_norm for term in ("وظيف", "تعيين", "الخدمه المدنيه", "الخدمة المدنية", "موظف"))
    impersonation_topic = any(term in topic_norm for term in ("انتحال", "حساب مزيف", "هويه مزيفه", "هوية مزيفة", "اسم كاذب"))
    if employment_topic:
        # Primary text of Law 14/2025 as published in the Official Gazette.
        official_employment_sources = [
            ("https://media.mof.gov.eg/mof-prd/qanwn_aleml_2025_14_f8e36d8b4f.pdf", "الجريدة الرسمية — وزارة المالية — قانون العمل رقم 14 لسنة 2025"),
            ("https://sis.gov.eg/media/760267/%D8%A7%D9%84%D9%82%D8%A7%D9%86%D9%88%D9%86-%D8%B1%D9%82%D9%85-14-%D9%84%D8%B3%D9%86%D8%A9-2025-%D8%A8%D8%A5%D8%B5%D8%AF%D8%A7%D8%B1-%D9%82%D8%A7%D9%86%D9%88%D9%86-%D8%A7%D9%84%D8%B9%D9%85%D9%84.pdf", "الجريدة الرسمية — الهيئة العامة للاستعلامات — قانون العمل رقم 14 لسنة 2025"),
            ("https://www.labour.gov.eg/media/0iedik3q/%D8%A7%D9%84%D9%82%D8%A7%D9%86%D9%88%D9%86-%D8%B1%D9%82%D9%85-14-%D9%84%D8%B3%D9%86%D8%A9-2025-%D8%A8%D8%A5%D8%B5%D8%AF%D8%A7%D8%B1-%D9%82%D8%A7%D9%86%D9%88%D9%86-%D8%A7%D9%84%D8%B9%D9%85%D9%84.pdf", "وزارة العمل — قانون العمل رقم 14 لسنة 2025"),
        ]
        for url, title in official_employment_sources:
            cand.append({"url": url, "title": title})
            seen.add(url)
    if cybercrime_topic or impersonation_topic:
        official_law_pdf = "https://fra.gov.eg/wp-content/uploads/2025/01/%D9%82%D8%A7%D9%86%D9%88%D9%86-%D8%B1%D9%82%D9%85-175-%D9%84%D8%B3%D9%86%D8%A9-2018-%D8%A8%D8%AA%D8%A7%D8%B1%D9%8A%D8%AE-2018-08-14.pdf"
        cand.append({"url": official_law_pdf, "title": "القانون رقم 175 لسنة 2018 — مكافحة جرائم تقنية المعلومات — الهيئة العامة للرقابة المالية"})
        seen.add(official_law_pdf)
    if public_service_topic:
        civil_service_pdf = "https://www.nosi.gov.eg/ar/Lists/NOSILibrary/%D9%82%D8%A7%D9%86%D9%88%D9%86%20%D8%A7%D9%84%D8%AE%D8%AF%D9%85%D8%A9%20%D8%A7%D9%84%D9%85%D8%AF%D9%86%D9%8A%D8%A9%2081%20%D9%84%D8%B3%D9%86%D8%A9%202016.pdf"
        cand.append({"url": civil_service_pdf, "title": "الجريدة الرسمية — قانون الخدمة المدنية رقم 81 لسنة 2016 — الهيئة القومية للتأمين الاجتماعي"})
        seen.add(civil_service_pdf)
        civil_service_rules = "https://www.caoa.gov.eg/WebForms/laws.aspx"
        cand.append({"url": civil_service_rules, "title": "الجهاز المركزي للتنظيم والإدارة — قوانين ومبادئ مستقرة واللائحة التنفيذية"})
        seen.add(civil_service_rules)
    if impersonation_topic:
        penal_code_url = "https://manshurat.org/node/14677"
        cand.append({"url": penal_code_url, "title": "قانون العقوبات رقم 58 لسنة 1937 — المواد 155 و156 و157 و336"})
        seen.add(penal_code_url)
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
            records.append(("judgment_or_principle",court,case,_date(body),_effective(body),x["title"],_quote(body,topic),x["url"],_source_evidence(body, topic)))
        elif _host_matches(d, OFFICIAL_LAWS):
            records.append(("current_legislation_source",d,"",_date(body),_effective(body),x["title"],"",x["url"],_source_evidence(body, topic)))
        elif _host_matches(d, SECONDARY_LAWS):
            records.append(("secondary_legislation_reference",d,"",_date(body),_effective(body),x["title"],"",x["url"],_source_evidence(body, topic)))
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
        lines += [f"SOURCE {i}",f"Type: {typ}",f"Court/source: {court}",f"Case number: {case or 'N/A'}",f"Date: {date or 'not stated'}",f"Effective/publication detail: {effective or 'not stated'}",f"Title: {title}",f"Verified short quotation: {quote or 'N/A'}",f"URL: {url}",f"VERIFIED SOURCE TEXT (retrieved): {evidence}",""]
    if existing: lines += ["EXISTING SHEET LEGAL SOURCES:",_clean(existing)[:8000]]
    return "\n".join(lines)
