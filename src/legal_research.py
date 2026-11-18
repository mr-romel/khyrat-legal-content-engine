from __future__ import annotations
import html as html_lib, re, io
from difflib import SequenceMatcher
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


def _research_topic_terms(topic: str) -> list[str]:
    """Extract topic terms generically; editorial angle suffixes are not legal subjects."""
    value = re.sub(
        r"(?i)(?:\s*[—–|:;,-]\s*)?(?:زاوية\s*(?:جديدة|أخرى|اخري|اخرى|مختلفة)|"
        r"check\s*[-_ ]?\s*list|checklist|content\s*angle|editorial\s*angle|"
        r"hook\s*pattern|خطة\s*المحتوى).*$",
        "",
        str(topic or ""),
    )
    normalized = _norm_legal_text(value)
    stop = {
        "قانون", "القانون", "مصر", "المصري", "المصرية", "بشأن", "بخصوص",
        "موضوع", "حالة", "حالات", "شرح", "معلومة", "علامات", "تحذيرية",
        "قبل", "بعد", "اتخاذ", "عملي", "عملية", "قائمة", "فحص",
        "checklist", "جديدة", "زاوية", "مختلفة", "عن", "في", "من", "على",
        "الى", "إلى", "و", "او", "أو", "مع", "هل", "كيف", "متى",
    }
    terms = []
    for token in re.findall(r"[\u0621-\u064A]{3,}", normalized):
        if token not in stop and token not in terms:
            terms.append(token)
    return terms[:8]


def _matching_source_words(terms: list[str], text: str) -> list[tuple[str, int]]:
    """Match exact words and close Arabic inflections without a per-topic synonym table."""
    words = [(match.group(0), match.start()) for match in re.finditer(r"[\u0621-\u064A]{3,}", text)]
    matched = []
    for term in terms:
        candidates = [
            (word, position) for word, position in words
            if word == term or (min(len(word), len(term)) >= 4 and SequenceMatcher(None, term, word).ratio() >= 0.72)
        ]
        if candidates:
            matched.extend(candidates[:4])
    return matched


def _source_evidence(text: str, topic: str) -> str:
    """Extract topic-matched passages from any Egyptian legal subject, not a topic whitelist."""
    value = _norm_legal_text(text)
    terms = _research_topic_terms(topic)
    if not value or not terms:
        return ""
    windows = []
    for matched_word, position in _matching_source_words(terms, value):
        start = max(0, position - 900)
        prefix = value[start:position]
        # If an article heading is nearby, start there rather than copying a long,
        # irrelevant introduction before the matching statutory passage.
        article_markers = list(re.finditer(r"(?:المادة|مادة)\s*(?:\(?\s*[٠-٩0-9]+\s*\)?)?", prefix))
        if article_markers:
            start += article_markers[-1].start()
        else:
            start = max(0, position - 140)
        end = min(len(value), position + 900)
        snippet = value[start:end].strip()
        if snippet and all(abs(start - old_start) > 240 for old_start, _ in windows):
            windows.append((start, snippet))
        if len(windows) >= 8:
            break
    if not windows:
        return ""
    law_refs = []
    law_pattern = r"(?:قانون|القانون)[^،؛.]{0,45}?(?:رقم\s*)?([٠-٩0-9]+)\s+لسنة\s+([٠-٩0-9]+)"
    for match in re.finditer(law_pattern, value, re.I):
        reference = f"قانون رقم {match.group(1)} لسنة {match.group(2)}"
        if reference not in law_refs:
            law_refs.append(reference)
    excerpts = [snippet for _, snippet in sorted(windows)]
    return _clean(" ".join(law_refs + excerpts))[:9000]

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
    text = str(packet or "").split("EXISTING SHEET LEGAL SOURCES:", 1)[0]
    blocks = re.split(r"(?m)^SOURCE\s+\d+\s*$", text)
    for block in blocks[1:]:
        match = re.search(r"(?m)^URL:\s*(https://\S+)", block)
        evidence = re.search(r"(?m)^VERIFIED SOURCE TEXT \(retrieved\):\s*(.{30,})$", block)
        title = re.search(r"(?m)^Title:\s*\S", block)
        if match and evidence and title and _allowed(match.group(1).rstrip(").,;")):
            return True
    return False


def research_legal_topic(topic, existing=""):
    """Discover and verify Egyptian legal sources for any topic through generic topic-first search."""
    raw_topic = _clean(topic)
    if not raw_topic:
        return _clean(existing)
    topic = re.sub(
        r"(?i)(?:\s*[—–|:;,-]\s*)?(?:زاوية\s*(?:جديدة|أخرى|اخري|اخرى|مختلفة)|"
        r"check\s*[-_ ]?\s*list|checklist|content\s*angle|editorial\s*angle|"
        r"hook\s*pattern|خطة\s*المحتوى).*$",
        "",
        raw_topic,
    ).strip()
    terms = _research_topic_terms(topic)
    if not terms:
        return (
            "LEGAL RESEARCH PACKET — VERIFIED WEB SOURCES ONLY\n"
            f"Research date: {datetime.now(timezone.utc).date().isoformat()}\n"
            f"Topic: {topic}\n"
            "No sufficiently specific legal search terms could be extracted automatically."
        )

    # Topic-first discovery across Egyptian courts, official government domains,
    # the Egyptian legislation portal and a secondary legal database.
    queries = [
        f'"{topic}" مصر قانون تشريع',
        f'"{topic}" نص قانوني مصر',
        f'site:cc.gov.eg/principle "{topic}"',
        f'site:esc.gov.eg "{topic}" حكم المحكمة الإدارية العليا',
        f'site:gov.eg "{topic}" قانون OR قرار OR لائحة',
        f'site:elpai.idsc.gov.eg "{topic}" تشريع',
        f'site:moj.gov.eg "{topic}" قانون',
        f'site:manshurat.org "{topic}" قانون مصر',
    ]
    candidates = []
    seen = set()
    for query in queries:
        for item in _search(query):
            url = str(item.get("url", "")).strip()
            if not url or url in seen or not _allowed(url):
                continue
            seen.add(url)
            candidates.append({"url": url, "title": str(item.get("title", "")).strip()})

    records = []
    fetch_limit = max(MAX_RESULTS, 12)
    for item in candidates[:fetch_limit]:
        url = item["url"]
        body = _fetch(url)
        if not body:
            continue
        evidence = _source_evidence(body, topic)
        if len(evidence) < 30:
            continue
        searchable = _norm_legal_text(item["title"] + " " + body)
        matched = [term for term in terms if _matching_source_words([term], searchable)]
        required_matches = 1 if len(terms) <= 2 else 2
        if len(set(matched)) < required_matches:
            continue

        domain = _domain(url)
        court = "محكمة النقض" if _host_matches(domain, COURT) else (
            "المحكمة الإدارية العليا" if _host_matches(domain, ADMIN) else domain
        )
        case = _case(body)
        if case and (_host_matches(domain, COURT) or _host_matches(domain, ADMIN)):
            source_type = "judgment_or_principle"
            quote = _quote(body, topic)
        elif _host_matches(domain, OFFICIAL_LAWS):
            source_type = "current_legislation_source"
            quote = ""
        elif _host_matches(domain, SECONDARY_LAWS):
            source_type = "secondary_legislation_reference"
            quote = ""
        else:
            continue
        records.append((
            source_type, court, case, _date(body), _effective(body),
            item["title"] or f"مصدر قانوني — {domain}", quote, url, evidence,
        ))
        if len(records) >= 6:
            break

    lines = [
        "LEGAL RESEARCH PACKET — VERIFIED WEB SOURCES ONLY",
        f"Research date: {datetime.now(timezone.utc).date().isoformat()}",
        f"Topic: {topic}",
        "",
        "AUTOMATIC RESEARCH METHOD: topic-first discovery across Egyptian court and government sources.",
        "WRITER RULES:",
        "- Use only sources retrieved successfully in this run and listed below.",
        "- Prefer the newest effective legislation; check publication and commencement dates.",
        "- If an amendment replaced an older rule, use the current effective rule and explain the change when material.",
        "- Quote only text actually retrieved from a source, max 24 words per source.",
        "- Every judicial quotation must include the verified court and exact case number.",
        "- Never invent a case number, date, quotation, statute number, or legal rule.",
        "- If no verified topic-matched source exists, do not invent a citation; keep the item blocked for legal review.",
        "",
    ]
    if not records:
        lines.append("No sufficiently verified topic-matched Egyptian court/legislation source was retrieved automatically.")
    for index, (kind, source, case, date, effective, title, quote, url, evidence) in enumerate(records, 1):
        lines += [
            f"SOURCE {index}", f"Type: {kind}", f"Court/source: {source}",
            f"Case number: {case or 'N/A'}", f"Date: {date or 'not stated'}",
            f"Effective/publication detail: {effective or 'not stated'}",
            f"Title: {title}", f"Verified short quotation: {quote or 'N/A'}",
            f"URL: {url}", f"VERIFIED SOURCE TEXT (retrieved): {evidence}", "",
        ]
    if existing:
        lines += ["EXISTING SHEET LEGAL SOURCES:", _clean(existing)[:8000]]
    return "\n".join(lines)
