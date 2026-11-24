from __future__ import annotations
import html as html_lib, re, io, os
from difflib import SequenceMatcher
from datetime import datetime, timezone
import time
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse
import requests

TIMEOUT=15
CURRENT_YEAR=datetime.now(timezone.utc).year
MAX_RESULTS=8
MAX_SOURCE_CHARS=250000
COURT=("cc.gov.eg","www.cc.gov.eg","sccourt.gov.eg","www.sccourt.gov.eg")
ADMIN=("esc.gov.eg","www.esc.gov.eg","stg.esc.gov.eg")
OFFICIAL_GOVERNMENT=("aca.gov.eg","www.aca.gov.eg","sis.gov.eg","www.sis.gov.eg","caoa.gov.eg","www.caoa.gov.eg","escc.gov.eg","www.escc.gov.eg")
OFFICIAL_LAWS=("fra.gov.eg","mof.gov.eg","elpai.idsc.gov.eg","gafi.gov.eg","eta.gov.eg","nosi.gov.eg","moi.gov.eg","cabinet.gov.eg","presidency.eg","moj.gov.eg","labour.gov.eg","parliament.gov.eg","mfa.gov.eg","mohp.gov.eg","moa.gov.eg","customs.gov.eg","esa.gov.eg","mcit.gov.eg","mti.gov.eg","moss.gov.eg","mohesr.gov.eg","moe.gov.eg","mld.gov.eg","mped.gov.eg","cairo.gov.eg","mwri.gov.eg")
SECONDARY_LAWS=("manshurat.org","www.manshurat.org","lawhub.info","www.lawhub.info")
LAWS=tuple(set(OFFICIAL_LAWS+SECONDARY_LAWS))

class _P(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag.lower() in {"script","style","noscript","svg"}: self.skip+=1
    def handle_endtag(self,tag):
        if tag.lower() in {"script","style","noscript","svg"} and self.skip: self.skip-=1
    def handle_data(self,data):
        if not self.skip and data.strip(): self.parts.append(data.strip())

class _SearchResults(HTMLParser):
    """Parse DuckDuckGo result anchors independent of HTML attribute order."""
    def __init__(self):
        super().__init__()
        self.items = []
        self._active = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs = dict(attrs)
        classes = str(attrs.get("class", "")).split()
        href = attrs.get("href", "")
        if "result__a" in classes and href:
            self._active = {"url": _unwrap(html_lib.unescape(href)), "title_parts": []}

    def handle_data(self, data):
        if self._active is not None and data.strip():
            self._active["title_parts"].append(data.strip())

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._active is not None:
            url = str(self._active.get("url", "")).strip()
            title = _clean(" ".join(self._active["title_parts"]))
            if url.startswith("http") and title:
                self.items.append({"url": url, "title": title})
            self._active = None


class _BingResults(HTMLParser):
    """Extract organic links from Bing result containers without depending on attribute order."""
    def __init__(self):
        super().__init__()
        self.items = []
        self._in_result = False
        self._active = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = str(attrs.get("class", "")).split()
        if tag.lower() in {"li", "div"} and "b_algo" in classes:
            self._in_result = True
        if self._in_result and tag.lower() == "a" and attrs.get("href") and self._active is None:
            href = html_lib.unescape(str(attrs["href"]))
            if href.startswith("http"):
                self._active = {"url": href, "title_parts": []}

    def handle_data(self, data):
        if self._active is not None and data.strip():
            self._active["title_parts"].append(data.strip())

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._active is not None:
            title = _clean(" ".join(self._active["title_parts"]))
            if title:
                self.items.append({"url": self._active["url"], "title": title})
            self._active = None
        elif tag.lower() in {"li", "div"} and self._in_result:
            self._in_result = False

def _clean(x): return re.sub(r"\s+"," ",str(x or "")).strip()
def _domain(u):
    return (urlparse(str(u or "")).hostname or "").lower().rstrip(".").removeprefix("www.")


def _host_matches(host, roots):
    host = str(host or "").lower().rstrip(".").removeprefix("www.")
    return any(host == root or host.endswith("." + root) for root in roots)
def _unwrap(u):
    q=parse_qs(urlparse(u).query).get("uddg",[""])[0]
    return unquote(q) if q else u

def _trusted_get(url, **kwargs):
    """Retry TLS validation with the OS trust store when certifi lacks a CA.

    Certificate verification is always enabled. This is a compatibility fallback
    for government endpoints whose certificate chain is trusted by the OS store
    but not by the Python certifi bundle.
    """
    try:
        return requests.get(url, **kwargs)
    except requests.exceptions.SSLError as initial_error:
        candidates = []
        configured = os.getenv("SSL_CERT_FILE", "").strip()
        if configured and os.path.isfile(configured):
            candidates.append(configured)
        system_bundle = "/etc/ssl/certs/ca-certificates.crt"
        if os.path.isfile(system_bundle) and system_bundle not in candidates:
            candidates.append(system_bundle)
        for ca_bundle in candidates:
            try:
                return requests.get(url, verify=ca_bundle, **kwargs)
            except requests.exceptions.SSLError:
                continue
        raise initial_error


def _dedupe_search_items(items):
    out, seen = [], set()
    for item in items:
        url = str(item.get("url", "")).strip()
        title = _clean(item.get("title", ""))
        if not url.startswith("https://") or not title or url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "title": title})
        if len(out) >= MAX_RESULTS:
            break
    return out


def _search(q):
    """Use DuckDuckGo first, then an independent Bing HTML result parser on empty/error responses."""
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"}
    ddg_items = []
    try:
        response = _trusted_get(
            "https://html.duckduckgo.com/html/",
            params={"q": q, "kl": "eg-ar"}, headers=headers, timeout=TIMEOUT,
        )
        response.raise_for_status()
        parser = _SearchResults()
        parser.feed(response.text)
        ddg_items = parser.items
    except Exception as exc:
        print(f"Legal research DuckDuckGo unavailable: {q!r} :: {exc}")

    results = _dedupe_search_items(ddg_items)
    if results:
        return results

    try:
        response = _trusted_get(
            "https://www.bing.com/search",
            params={"q": q, "cc": "EG", "setlang": "ar"},
            headers=headers, timeout=TIMEOUT,
        )
        response.raise_for_status()
        parser = _BingResults()
        parser.feed(response.text)
        results = _dedupe_search_items(parser.items)
        if results:
            print(f"Legal research fallback search recovered {len(results)} results via Bing.")
            return results
        print(f"Legal research fallback search returned no parseable organic results: {q!r}")
    except Exception as exc:
        print(f"Legal research Bing fallback unavailable: {q!r} :: {exc}")
    return results

def _fetch(u):
    """Fetch source text with bounded retries for transient transport/server failures only."""
    response = None
    for attempt in range(2):
        try:
            response = _trusted_get(
                u,
                headers={"User-Agent": "Mozilla/5.0 Khyrat-Legal-Content-Engine/1.0"},
                timeout=TIMEOUT,
            )
            if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                print(f"Legal source transient HTTP {response.status_code}; retrying once: {u}")
                time.sleep(0.5)
                continue
            response.raise_for_status()
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            if attempt == 0:
                print(f"Legal source transient transport error; retrying once: {u} :: {exc}")
                time.sleep(0.5)
                continue
            print(f"Legal research source unavailable after retry: {u} :: {exc}")
            return ""
        except Exception as exc:
            print(f"Legal research source unavailable: {u} :: {exc}")
            return ""
    if response is None:
        return ""
    content_type = response.headers.get("content-type", "").lower()
    if "pdf" in content_type or urlparse(u).path.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(response.content))
            plain_parts = []
            layout_parts = []
            for page in reader.pages:
                try:
                    plain_parts.append(page.extract_text() or "")
                except Exception:
                    plain_parts.append("")
                try:
                    layout_parts.append(page.extract_text(extraction_mode="layout") or "")
                except Exception:
                    layout_parts.append("")
            candidates = [
                _clean(" ".join(plain_parts)),
                _clean(" ".join(layout_parts)),
            ]
            # Arabic PDFs sometimes expose usable text only through layout extraction.
            # Prefer the candidate containing the most Arabic code points, not the
            # longest string, so broken font-map noise cannot win.
            extracted = max(
                candidates,
                key=lambda value: sum("\u0600" <= char <= "\u06FF" for char in value),
            )
            arabic_chars = sum("\u0600" <= char <= "\u06FF" for char in extracted)
            print(
                f"Legal PDF extraction completed: chars={len(extracted)}; "
                f"arabic_chars={arabic_chars}; url={u}"
            )
            return extracted[:MAX_SOURCE_CHARS]
        except Exception as pdf_exc:
            print(f"Legal PDF text extraction unavailable: {u} :: {pdf_exc}")
            return ""
    try:
        parser = _P()
        parser.feed(response.text)
        return _clean(" ".join(parser.parts))[:MAX_SOURCE_CHARS]
    except Exception as parse_exc:
        print(f"Legal source HTML parsing failed: {u} :: {parse_exc}")
        return ""

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



def _topic_evidence_terms(topic: str) -> list[str]:
    """Expand editorial topic wording into legally equivalent source terminology."""
    normalized = _norm_legal_text(topic)
    terms = list(_research_topic_terms(topic))
    aliases = []
    if "انتحال" in normalized or "الشخصيه" in normalized:
        aliases.extend([
            "انتحال صفة", "صفة كاذبة", "صفة غير صحيحة", "انتحال صفة موظف عام",
            "اسم كاذب", "تداخل في وظيفة عمومية", "صفة رسمية من الحكومة",
            "اختلاس الألقاب والوظائف", "الاتصاف بها بدون حق",
        ])
    if any(term in normalized for term in ("الحياة الخاصة", "انتهاك حرمة", "خصوصية")):
        aliases.extend([
            "انتهاك حرمة الحياة الخاصة", "الاعتداء على حرمة الحياة الخاصة",
            "خصوصية أي شخص دون رضاه", "نشر معلومات أو صور تنتهك الخصوصية",
            "تسجيل أو نقل محادثات في مكان خاص", "التقاط صورة شخص في مكان خاص",
            "قانون مكافحة جرائم تقنية المعلومات", "المادة 25",
            "المادة 309 مكرر", "قانون العقوبات",
        ])
    if "امتناع" in normalized and "الادارة" in normalized:
        aliases.extend([
            "امتناع الإدارة", "رفض السلطات الإدارية", "القرارات الإدارية",
            "قرار إداري سلبي", "اتخاذ قرار",
        ])
    if any(term in normalized for term in ("وظيفه", "الوظيفه", "تعيين", "الخدمه المدنيه")):
        aliases.extend([
            "الوظائف المدنية حق للمواطنين", "الكفاءة والجدارة",
            "التعيين بموجب قرار", "شغل الوظائف", "الوظائف الشاغرة والممولة",
            "امتحان ينفذه الجهاز", "لجنة للاختيار", "شروط شغل الوظائف",
            "الخدمة المدنية", "الوظائف العامة", "الوظائف المدنية", "الوظيفة المدنية",
            "التعيين في الوظائف", "قانون الخدمة المدنية",
            "قانون الخدمة المدنية رقم 81 لسنة 2016", "وظائف شاغرة وممولة",
            "لجنة الاختيار", "امتحان التعيين", "المادة 12",
        ])
    for alias in aliases:
        for token in re.findall(r"[\u0621-\u064A]{3,}", _norm_legal_text(alias)):
            if token not in terms:
                terms.append(token)
    if any(term in normalized for term in ("وظيفه", "الوظيفه", "تعيين", "الخدمه المدنيه")):
        for token in ("الوظائف", "المدنية", "الكفاءة", "الجدارة", "التعيين", "شاغرة", "ممولة", "الامتحان"):
            if token not in terms:
                terms.append(token)
    return terms

def _matching_source_words(terms: list[str], text: str) -> list[tuple[str, int]]:
    """Match exact words and close Arabic inflections without a per-topic synonym table."""
    words = [(match.group(0), match.start()) for match in re.finditer(r"[\u0621-\u064A]{3,}", text)]
    matched = []
    for term in terms:
        candidates = [
            (word, position) for word, position in words
            if word == term or (min(len(word), len(term)) >= 5 and SequenceMatcher(None, term, word).ratio() >= 0.62)
        ]
        if candidates:
            matched.extend(candidates[:4])
    return matched


def _source_evidence(text: str, topic: str) -> str:
    """Extract topic-matched passages from any Egyptian legal subject, not a topic whitelist."""
    value = _norm_legal_text(text)
    terms = _topic_evidence_terms(topic)
    if not value or not terms:
        return ""
    windows = []
    for matched_word, position in _matching_source_words(terms, value):
        start = max(0, position - 900)
        prefix = value[start:position]
        # If an article heading is nearby, start there rather than copying a long,
        # irrelevant introduction before the matching statutory passage.
        article_markers = list(re.finditer(r"(?:المادة|مادة)\s*(?:\(?\s*[٠-٩0-9]+\s*\)?)?", prefix))
        following = value[position:min(len(value), position + 320)]
        article_after = re.search(r"(?:المادة|مادة)\s*(?:\(?\s*[٠-٩0-9]+\s*\)?)?", following)
        if article_after:
            start = position + article_after.start()
        elif article_markers:
            start += article_markers[-1].start()
        else:
            start = max(0, position - 80)
        end = min(len(value), max(position + 900, start + 900))
        snippet = value[start:end].strip()
        if snippet and all(abs(start - old_start) > 240 for old_start, _ in windows):
            windows.append((start, snippet))
        if len(windows) >= 8:
            break
    if not windows:
        return ""
    # Preserve exact statutory identifiers from the successfully fetched source body.
    # Topic excerpts are intentionally short, but citation validation must also see
    # article/law references elsewhere in that same retrieved document.
    law_refs = []
    law_pattern = r"(?:قانون|القانون)[^،؛.]{0,80}?(?:رقم\s*)?([٠-٩0-9]+)\s+لسنة\s+([٠-٩0-9]+)"
    for match in re.finditer(law_pattern, value, re.I):
        reference = f"قانون رقم {match.group(1)} لسنة {match.group(2)}"
        if reference not in law_refs:
            law_refs.append(reference)

    article_refs = []
    article_pattern = r"(?:المادة|مادة)\s*[（(]?\s*([٠-٩0-9]+)\s*[）)]?"
    # Article numbers are admitted only when they occur in a topic-matched excerpt,
    # not merely somewhere in an unrelated part of a large statute.
    for _, snippet in windows:
        for match in re.finditer(article_pattern, snippet, re.I):
            reference = f"المادة {match.group(1)}"
            if reference not in article_refs:
                article_refs.append(reference)

    excerpts = [snippet for _, snippet in sorted(windows)]
    return _clean(" ".join(law_refs + article_refs + excerpts))[:9000]

def _quote(t,topic,max_words=24):
    terms=[x for x in re.findall(r"[\u0600-\u06ff]{4,}",topic) if x not in {"قانون","مصر","الموضوع"}]
    # Short, complete sentences can still be meaningful source quotations.
    ss=[s.strip() for s in re.split(r"(?<=[.!؟])\s+",t) if 5<=len(s.split())<=80]
    if not ss:return ""
    ss.sort(key=lambda s:sum(term in s for term in terms),reverse=True)
    return _clean(" ".join(ss[0].split()[:max_words]))
def _allowed(u):
    parsed = urlparse(str(u or ""))
    host = (parsed.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    trusted_roots = {
        str(root).lower().removeprefix("www.").rstrip(".")
        for root in (*COURT, *ADMIN, *OFFICIAL_GOVERNMENT, *OFFICIAL_LAWS, *SECONDARY_LAWS)
    }
    return parsed.scheme.lower() == "https" and bool(host) and any(
        host == root or host.endswith("." + root)
        for root in trusted_roots
    )



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
    source_blocks = re.split(r"(?m)^SOURCE\s+\d+\s*$", verified_packet)
    eligible_evidence = [source_blocks[0]]
    for block in source_blocks[1:]:
        source_type = re.search(r"(?m)^Type:\s*(\S+)", block)
        # Only explicitly typed primary/official source blocks can verify
        # precise legal citations. Secondary, missing-type, and unknown blocks
        # remain context only and cannot satisfy this evidentiary requirement.
        if not source_type or source_type.group(1) not in {
            "current_legislation_source", "judgment_or_principle", "official_government_source"
        }:
            continue
        eligible_evidence.append(block)
    normalized_evidence = _norm_legal_text("\n".join(eligible_evidence))

    issues: list[str] = []
    if "قانون الادارة العامة" in normalized_post:
        issues.append("اسم تشريع غير موثق/مريب: قانون الإدارة العامة؛ احذف الإسناد أو استبدله بنص مصري محدد تم التحقق منه.")

    for claim in extract_precise_legal_claims(value):
        if _norm_legal_text(claim) not in normalized_evidence:
            issues.append(f"إحالة قانونية دقيقة لم تظهر حرفيًا في أدلة المصادر المسترجعة: {claim}")
    return list(dict.fromkeys(issues))



def has_verified_legal_source(packet: str) -> bool:
    """Require a retrieved, whitelisted primary/official source block.

    Secondary legal databases remain useful research leads, but they cannot
    independently satisfy the publication source gate.
    """
    text = str(packet or "").split("EXISTING SHEET LEGAL SOURCES:", 1)[0]
    blocks = re.split(r"(?m)^SOURCE\s+\d+\s*$", text)
    allowed_types = {"current_legislation_source", "judgment_or_principle", "official_government_source"}
    for block in blocks[1:]:
        match = re.search(r"(?m)^URL:\s*(https://\S+)", block)
        source_type = re.search(r"(?m)^Type:\s*(\S+)", block)
        evidence = re.search(r"(?m)^VERIFIED SOURCE TEXT \(retrieved\):\s*(.{30,})$", block)
        title = re.search(r"(?m)^Title:\s*\S", block)
        if (
            match and source_type and source_type.group(1) in allowed_types
            and evidence and title and _allowed(match.group(1).rstrip(").,;"))
        ):
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
    terms = _topic_evidence_terms(topic)
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
        f'site:cc.gov.eg "{topic}"',
        f'site:sccourt.gov.eg "{topic}" حكم OR مبدأ',
        f'site:esc.gov.eg "{topic}" حكم المحكمة الإدارية العليا',
        f'site:aca.gov.eg "{topic}"',
        f'site:gov.eg "{topic}" قانون OR قرار OR لائحة',
        f'site:elpai.idsc.gov.eg "{topic}" تشريع',
        f'site:moj.gov.eg "{topic}" قانون',
        f'site:manshurat.org "{topic}" قانون مصر',
    ]

    # Universal semantic reformulations: derive additional searches from the
    # actual topic terms instead of relying on a hand-maintained topic whitelist.
    # This runs for every legal subject, including newly added queue topics.
    generic_terms = [term for term in terms if len(term) >= 3][:5]
    if generic_terms:
        compact_topic = " ".join(generic_terms[:3])
        queries.extend([
            f'"{compact_topic}" قانون مصري',
            f'"{compact_topic}" مادة تشريع مصر',
            f'"{compact_topic}" حكم قضائي مبدأ',
            f'"{compact_topic}" قرار إداري لائحة',
            f'site:gov.eg "{compact_topic}"',
            f'site:*.gov.eg "{compact_topic}" قانون OR قرار',
        ])

    # Small semantic query expansions for the two current queue subjects. These
    # are discovery terms only; a source still must pass live retrieval and topic evidence.
    normalized_topic = _norm_legal_text(topic)
    if any(term in normalized_topic for term in ("الحياة الخاصة", "انتهاك حرمة", "خصوصية")):
        queries.extend([
            'site:escc.gov.eg/assets/docs/law-175-2018.pdf "حرمة الحياة الخاصة"',
            'site:register.cc.gov.eg "انتهاك حرمة الحياة الخاصة"',
            'site:register.cc.gov.eg "المادة 25" "القانون 175"',
            'site:fra.gov.eg "حرمة الحياة الخاصة" "قانون 175 لسنة 2018"',
            'site:cc.gov.eg "309 مكرر" "حرمة الحياة الخاصة"',
            '"انتهاك حرمة الحياة الخاصة" "القانون رقم 175 لسنة 2018" مصر',
        ])
    if "انتحال" in normalized_topic:
        queries.extend([
            'site:aca.gov.eg "انتحال صفة" موظف عام',
            'site:cc.gov.eg "انتحال صفة كاذبة"',
            'site:sccourt.gov.eg "انتحال صفة" قانون العقوبات',
        ])
    if any(term in normalized_topic for term in ("وظيفه", "الوظيفه", "تعيين", "الخدمه المدنيه")):
        queries.extend([
            'site:nosi.gov.eg "قانون الخدمة المدنية" 81 2016',
            'site:caoa.gov.eg "قانون الخدمة المدنية" التعيين',
            'site:mof.gov.eg "قانون الخدمة المدنية" 81 2016',
        ])
    candidates = []
    seen = set()

    # Revalidate previously stored source URLs before fresh discovery. This is a
    # cross-run cache optimization, not a trust shortcut: every URL is fetched
    # again and must pass the current topic-evidence and official-domain gates.
    existing_packet = str(existing or "").split("EXISTING SHEET LEGAL SOURCES:", 1)[0]
    cached_blocks = re.split(r"(?m)^SOURCE\s+\d+\s*$", existing_packet)
    for block in cached_blocks[1:]:
        url_match = re.search(r"(?m)^URL:\s*(https://\S+)", block)
        title_match = re.search(r"(?m)^Title:\s*(.+)$", block)
        cached_url = url_match.group(1).rstrip(").,;") if url_match else ""
        cached_title = title_match.group(1).strip() if title_match else ""
        if cached_url and _allowed(cached_url) and cached_url not in seen:
            seen.add(cached_url)
            candidates.append({"url": cached_url, "title": cached_title or "Previously verified legal source — revalidation required"})

    # Verified official landing documents for the two queue topics. They are
    # still fetched live and must pass the same text/topic evidence checks below.
    normalized_for_seeds = _norm_legal_text(topic)
    seed_urls = []
    if any(term in normalized_for_seeds for term in ("انتهاء الخدمه", "انتهاء الخدمة", "انتهاء خدمه")):
        seed_urls.extend([
            (
                "https://www.mwri.gov.eg/wp-content/uploads/2019/12/Civil-Service-Law.pdf",
                "الجريدة الرسمية — قانون الخدمة المدنية رقم 81 لسنة 2016، الباب الثامن انتهاء الخدمة والمواد 69 إلى 72، نسخة منشورة على موقع وزارة الموارد المائية والري",
            ),
            (
                "https://www.esa.gov.eg/files/laws/10.pdf",
                "الجريدة الرسمية — قانون الخدمة المدنية رقم 81 لسنة 2016، الباب الثامن انتهاء الخدمة والمواد 69 إلى 72، نسخة منشورة على موقع وكالة الفضاء المصرية",
            ),
            (
                "https://www.nosi.gov.eg/ar/Lists/NOSILibrary/قانون%20الخدمة%20المدنية%2081%20لسنة%202016.pdf",
                "الهيئة القومية للتأمين الاجتماعي — النص المنشور لقانون الخدمة المدنية رقم 81 لسنة 2016، الباب الثامن انتهاء الخدمة",
            ),
        ])
    if "انتحال" in normalized_for_seeds:
        seed_urls.extend([
            ("https://aca.gov.eg/News/1550.aspx", "الرقابة الإدارية: انتحال صفة الموظفين العموميين"),
            ("https://cc.gov.eg/heritage/index-entries?book=42&page=10", "محكمة النقض: انتحال صفة كاذبة"),
            ("https://aca.gov.eg/Media/News/2021/12/11/2021-637748484788261346-826.pdf", "هيئة الرقابة الإدارية: استغلال صفة الموظف العام"),
            ("https://manshurat.org/node/14677", "قانون العقوبات رقم 58 لسنة 1937 — الباب العاشر، المواد 155 إلى 157"),
        ])
    if "امتناع" in normalized_for_seeds and "الادارة" in normalized_for_seeds:
        seed_urls.extend([
            (
                "https://esc.gov.eg/service/%D8%A7%D9%84%D9%82%D8%B3%D9%85-%D8%A7%D9%84%D9%82%D8%B6%D8%A7%D8%A6%D9%8A/",
                "مجلس الدولة المصري — اختصاص القضاء الإداري وحكم الامتناع عن اتخاذ القرار",
            ),
            (
                "https://stg.esc.gov.eg/%D8%A7%D9%84%D9%82%D8%B3%D9%85-%D8%A7%D9%84%D9%82%D8%B6%D8%A7%D8%A6%D9%8A/",
                "مجلس الدولة المصري — القسم القضائي (نطاق فرعي رسمي stg)",
            ),
            (
                "https://mof.gov.eg/ar/legislation/legislation-5fe86ada7bfc600007cc01b8",
                "وزارة المالية — قانون مجلس الدولة رقم 47 لسنة 1972 وحالته التشريعية",
            ),
        ])
    if any(term in normalized_for_seeds for term in ("وظيفه", "الوظيفه", "تعيين", "الخدمه المدنيه")):
        seed_urls.extend([
            (
                "https://www.mwri.gov.eg/wp-content/uploads/2019/12/Civil-Service-Law.pdf",
                "الجريدة الرسمية — قانون الخدمة المدنية رقم 81 لسنة 2016، نسخة منشورة على موقع وزارة الموارد المائية والري",
            ),
            (
                "https://www.esa.gov.eg/files/laws/10.pdf",
                "الجريدة الرسمية — قانون الخدمة المدنية رقم 81 لسنة 2016، نسخة منشورة على موقع وكالة الفضاء المصرية",
            ),
            (
                "https://www.cairo.gov.eg/ar/Monthly%20Publication/%D9%86%D8%B4%D8%B1%D8%A9%20%D9%81%D8%A8%D8%B1%D8%A7%D9%8A%D8%B12019%20.pdf",
                "محافظة القاهرة — نسخة منشورة من قانون الخدمة المدنية في النشرة الرسمية لشهر فبراير 2019",
            ),
            (
                "https://jobs.caoa.gov.eg/",
                "الجهاز المركزي للتنظيم والإدارة — بوابة الوظائف الحكومية، الوظائف التي تشغل بالتعيين والتعاقد ومكتبة قانون الخدمة المدنية",
            ),
            (
                "https://www.caoa.gov.eg/WebForms/laws.aspx",
                "الجهاز المركزي للتنظيم والإدارة — مكتبة قوانين ومبادئ مستقرة، قانون الخدمة المدنية رقم 81 لسنة 2016",
            ),
            (
                "https://aca.gov.eg/News/1625.aspx",
                "هيئة الرقابة الإدارية — الإطار التشريعي لقانون الخدمة المدنية رقم 81 لسنة 2016 وطرق التعيين",
            ),
            (
                "https://sccourt.gov.eg/DjangoPortalResources/Rules_Html/10425_35_105_1_2.html",
                "المحكمة الدستورية العليا — حكم بشأن موضوعية شروط شغل الوظائف العامة ومبدأ الجدارة",
            ),
            (
                "https://customs.gov.eg/Upload/ECAAdminace/54f10188-271f-4255-93f2-2f722a46f244.pdf",
                "الجريدة الرسمية — قانون الخدمة المدنية رقم 81 لسنة 2016، نسخة منشورة على موقع مصلحة الجمارك",
            ),
            (
                "https://www.esa.gov.eg/files/laws/10.pdf",
                "الجريدة الرسمية — قانون الخدمة المدنية رقم 81 لسنة 2016، نسخة منشورة على موقع وكالة الفضاء المصرية",
            ),
            (
                "https://moa.gov.eg/media/i30diigu/%D9%82%D8%A7%D9%86%D9%88%D9%86-%D8%A7%D9%84%D8%AE%D8%AF%D9%85%D8%A9-%D8%A7%D9%84%D9%85%D8%AF%D9%86%D9%8A%D8%A9.pdf",
                "الجريدة الرسمية — قانون الخدمة المدنية رقم 81 لسنة 2016، نسخة منشورة على موقع وزارة الزراعة",
            ),
            (
                "https://www.nosi.gov.eg/ar/Lists/NOSILibrary/قانون%20الخدمة%20المدنية%2081%20لسنة%202016.pdf",
                "قانون الخدمة المدنية رقم 81 لسنة 2016 — الجريدة الرسمية عبر الهيئة القومية للتأمين الاجتماعي",
            ),
            (
                "https://www.cairo.gov.eg/ar/Monthly%20Publication/%D9%86%D8%B4%D8%B1%D8%A9%20%D9%81%D8%A8%D8%B1%D8%A7%D9%8A%D8%B12019.pdf",
                "محافظة القاهرة: نشر رسمي يتضمن قانون الخدمة المدنية رقم 81 لسنة 2016",
            ),
            (
                "https://mof.gov.eg/ar/legislation/legislation-5fe868ed7bfc600007cbeec5",
                "وزارة المالية: قانون الخدمة المدنية رقم 81 لسنة 2016 — الحالة المنشورة للقانون",
            ),
            (
                "https://manshurat.org/node/14678",
                "قانون الخدمة المدنية رقم 81 لسنة 2016 — النص الكامل والمواد المنظمة للتعيين",
            ),
        ])
    if any(term in normalized_for_seeds for term in ("الحياة الخاصة", "انتهاك حرمة", "خصوصية")):
        seed_urls.extend([
            (
                "https://www.fra.gov.eg/wp-content/uploads/2025/01/%D9%82%D8%A7%D9%86%D9%88%D9%86-%D8%B1%D9%82%D9%85-175-%D9%84%D8%B3%D9%86%D8%A9-2018-%D8%A8%D8%AA%D8%A7%D8%B1%D9%8A%D8%AE-2018-08-14.pdf",
                "الهيئة العامة للرقابة المالية — نسخة منشورة من القانون رقم 175 لسنة 2018 بشأن مكافحة جرائم تقنية المعلومات",
            ),
            (
                "https://fra.gov.eg/regulations/%D9%82%D8%A7%D9%86%D9%88%D9%86-%D8%B1%D9%82%D9%85-175-%D9%84%D8%B3%D9%86%D8%A9-2018/",
                "الهيئة العامة للرقابة المالية — صفحة القانون رقم 175 لسنة 2018",
            ),
            (
                "https://escc.gov.eg/assets/docs/law-175-2018.pdf",
                "الجريدة الرسمية — القانون رقم 175 لسنة 2018 بشأن مكافحة جرائم تقنية المعلومات، الفصل الثالث والمادة 25",
            ),
            (
                "https://register.cc.gov.eg/publications/159/download",
                "محكمة النقض المصرية — مبدأ قضائي رسمي بشأن الاعتداء على حرمة الحياة الخاصة وفق المادة 309 مكرراً عقوبات",
            ),
        ])
    for url, title in seed_urls:
        if _allowed(url) and url not in seen:
            seen.add(url)
            candidates.append({"url": url, "title": title})

    search_result_count = 0
    rejected_domain_count = 0
    if seed_urls:
        # Topic-specific official documents are fetched and text-verified below.
        # Avoid spending minutes on unavailable HTML search providers when a
        # primary-source retrieval path is already known for this subject.
        print(
            "Legal research: using topic-specific official source seeds first; "
            f"external discovery skipped for this seeded topic ({len(seed_urls)} source(s))."
        )
        queries = []
    for query in queries:
        found = _search(query)
        search_result_count += len(found)
        for item in found:
            url = str(item.get("url", "")).strip()
            if not url or url in seen:
                continue
            if not _allowed(url):
                rejected_domain_count += 1
                continue
            seen.add(url)
            candidates.append({"url": url, "title": str(item.get("title", "")).strip()})

    print(
        "Legal research diagnostics: "
        f"topic={topic!r}; queries={len(queries)}; search_results={search_result_count}; "
        f"whitelisted_candidates={len(candidates)}; rejected_domains={rejected_domain_count}; "
        f"seed_candidates={len(seed_urls)}"
    )

    records = []
    fetch_limit = max(MAX_RESULTS, 12)
    for item in candidates[:fetch_limit]:
        url = item["url"]
        body = _fetch(url)
        if not body:
            print(f"Legal research candidate rejected: empty/unreadable source body :: {url}")
            continue
        evidence = _source_evidence(body, topic)
        if len(evidence) < 30:
            print(f"Legal research candidate rejected: no topic-matched passage :: {url}")
            continue
        searchable = _norm_legal_text(item["title"] + " " + body)
        matched = [term for term in terms if _matching_source_words([term], searchable)]
        required_matches = 1
        if len(set(matched)) < required_matches:
            print(f"Legal research candidate rejected: insufficient topic-term matches ({len(set(matched))}/{required_matches}) :: {url}")
            continue

        domain = _domain(url)
        court = "محكمة النقض" if _host_matches(domain, COURT) else (
            "المحكمة الإدارية العليا" if _host_matches(domain, ADMIN) else domain
        )
        case = _case(body)
        if _host_matches(domain, COURT):
            source_type = "judgment_or_principle"
            # Never invent a case number; a source without one may be cited without a quotation.
            quote = _quote(body, topic) if case else ""
        elif _host_matches(domain, ADMIN):
            # The official State Council website is an institutional source,
            # not a retrieved judicial ruling; classify it accordingly.
            source_type = "official_government_source"
            quote = ""
        elif _host_matches(domain, OFFICIAL_LAWS):
            # A government index page that only reports a law's current status
            # is not the law text and cannot verify its substantive provisions.
            status_only_mof_page = (
                _host_matches(domain, ("mof.gov.eg",))
                and "حالة القانون" in body
                and not re.search(r"(?:المادة|مادة)\s*[（(]?\s*[٠-٩0-9]+", body)
            )
            source_type = "legislation_status_source" if status_only_mof_page else "current_legislation_source"
            quote = ""
        elif _host_matches(domain, OFFICIAL_GOVERNMENT):
            source_type = "official_government_source"
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
        print(f"Legal research candidate accepted: {domain} :: {url}")
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
        print(
            "Legal research final result: BLOCKED; "
            f"topic={topic!r}; candidates={len(candidates)}; no live source passed retrieval and topic-evidence validation."
        )
        lines.append("No sufficiently verified topic-matched Egyptian court/legislation source was retrieved automatically.")
    else:
        print(f"Legal research final result: VERIFIED; topic={topic!r}; sources={len(records)}")
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
