from __future__ import annotations

import html, json, os, re, hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from blogger_editor import prepare_article

BLOGGER_SCOPE = "https://www.googleapis.com/auth/blogger"
DEFAULT_BLOG_URL = "https://askmahmoudkhyrat.blogspot.com/"
FACEBOOK_URL = "https://www.facebook.com/AskMahmoudNow"
LINKEDIN_URL = "https://www.linkedin.com/in/mahmoud-khyrat"
BLOGGER_URL = "https://askmahmoudkhyrat.blogspot.com/?m=1"
WHATSAPP_URL = "https://wa.me/201022718375"
SUGGEST_URL = "https://suggestqueries.google.com/complete/search"

class BloggerPublishError(RuntimeError): pass

def _clean(v: Any) -> str: return " ".join(str(v or "").strip().split())


def normalize_blogger_labels(values: list[Any], *, max_total_chars: int = 180, max_labels: int = 10) -> list[str]:
    """Return unique Blogger labels below the 200-character combined UI limit."""
    labels: list[str] = []
    seen: set[str] = set()
    total = 0
    for raw in values or []:
        label = re.sub(r"[\r\n,]+", " ", _clean(raw))
        label = re.sub(r"\s+", " ", label).strip()[:40].strip()
        key = label.casefold()
        if not label or key in seen:
            continue
        addition = len(label) + (2 if labels else 0)
        if total + addition > max_total_chars:
            continue
        labels.append(label)
        seen.add(key)
        total += addition
        if len(labels) >= max_labels:
            break
    return labels

_EDITORIAL_META_RE = re.compile(r"(?:زاوية\s*(?:المحتوى|المقال)?|زاوية\s*جديدة|الهدف|الهدف\s*من\s*المحتوى|pillar|objective|hook|cta|نوع\s*المحتوى|خطة\s*المحتوى)", re.IGNORECASE)

def _strip_editorial_metadata(text: str) -> str:
    value = str(text or "")
    value = _EDITORIAL_META_RE.sub("", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()

def _article_copy(article: dict[str, Any]) -> dict[str, Any]:
    out = dict(article or {})
    out["title"] = _strip_editorial_metadata(out.get("title", ""))
    out["lead"] = _strip_editorial_metadata(out.get("lead", ""))
    for key in ("meta_description", "excerpt"):
        out[key] = _strip_editorial_metadata(out.get(key, ""))
    sections = []
    for item in out.get("sections", []) if isinstance(out.get("sections"), list) else []:
        if isinstance(item, dict):
            sections.append({"heading": _strip_editorial_metadata(item.get("heading", "")),
                             "body": _strip_editorial_metadata(item.get("body", ""))})
    out["sections"] = sections
    faq = []
    for item in out.get("faq", []) if isinstance(out.get("faq"), list) else []:
        if isinstance(item, dict):
            faq.append({"question": _strip_editorial_metadata(item.get("question", "")),
                        "answer": _strip_editorial_metadata(item.get("answer", ""))})
    out["faq"] = faq
    return out

def _safe_filename(v: str) -> str:
    return (re.sub(r"\s+", "_", re.sub(r"[^\w\-\u0600-\u06ff ]+", "", str(v or ""), flags=re.UNICODE).strip())[:90] or "legal_article")

def _credentials() -> Credentials:
    raw = os.getenv("BLOGGER_OAUTH_JSON", "").strip()
    if not raw: raise BloggerPublishError("BLOGGER_OAUTH_JSON is missing.")
    try: info = json.loads(raw)
    except json.JSONDecodeError as exc: raise BloggerPublishError("BLOGGER_OAUTH_JSON is not valid JSON.") from exc
    try: c = Credentials.from_authorized_user_info(info, scopes=[BLOGGER_SCOPE])
    except Exception as exc: raise BloggerPublishError(f"Invalid Blogger OAuth credentials: {exc}") from exc
    if c.expired and c.refresh_token:
        try: c.refresh(Request())
        except Exception as exc: raise BloggerPublishError(f"Blogger OAuth refresh failed: {exc}") from exc
    if not c.valid: raise BloggerPublishError("Blogger OAuth credentials are not valid.")
    return c

def service():
    return build("blogger", "v3", credentials=_credentials(), cache_discovery=False)

def upload_blogger_image(image_path: str) -> str:
    """Upload an image to Blogger's own photo storage and return a direct URL."""
    path = Path(image_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise BloggerPublishError(f"Blogger image file is missing: {path}")
    creds = _credentials()
    token = creds.token
    size = path.stat().st_size
    filename = path.name
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    url = "https://docs.google.com/upload/blogger/photos/resumable"
    params = {"authuser": "0", "opi": "98421741"}
    payload = {"protocolVersion": "0.8", "createSessionRequest": {"fields": [
        {"external": {"name": "file", "filename": filename, "put": {}, "size": size}},
        {"inlined": {"name": "title", "content": filename, "contentType": "text/plain"}},
        {"inlined": {"name": "onepick_version", "content": "v2", "contentType": "text/plain"}},
        {"inlined": {"name": "onepick_host_id", "content": "10", "contentType": "text/plain"}},
        {"inlined": {"name": "onepick_host_usecase", "content": "RichEditor", "contentType": "text/plain"}},
        {"inlined": {"name": "album_mode", "content": "permanent", "contentType": "text/plain"}},
        {"inlined": {"name": "silo_id", "content": "3", "contentType": "text/plain"}},
    ]}}
    session = requests.Session()
    last_error = None
    for attempt in range(1, 6):
        try:
            headers = {"x-client-pctx": "CgcSBWjtl_cu", "x-goog-upload-command": "start",
                       "x-goog-upload-header-content-length": str(size),
                       "x-goog-upload-header-content-type": mime, "x-goog-upload-protocol": "resumable",
                       "authorization": f"Bearer {token}", "content-type": "application/x-www-form-urlencoded"}
            start = session.post(url, data=json.dumps(payload), headers=headers, params=params, timeout=60)
            if start.status_code in {401, 403} and creds.refresh_token:
                creds.refresh(Request()); token = creds.token; continue
            start.raise_for_status()
            upload_url = start.headers.get("x-goog-upload-url")
            if not upload_url:
                raise RuntimeError(f"Blogger did not return upload URL: {start.text[:1000]}")
            upload_headers = {"accept": "*/*", "content-type": mime, "origin": "https://docs.google.com",
                              "referer": "https://docs.google.com/", "user-agent": "Mozilla/5.0",
                              "x-client-pctx": "CgcSBWjtl_cu", "x-goog-upload-command": "upload, finalize",
                              "x-goog-upload-offset": "0"}
            done = session.post(upload_url, headers=upload_headers, data=path.read_bytes(), timeout=180)
            done.raise_for_status()
            info = done.json()["sessionStatus"]["additionalInfo"]["uploader_service.GoogleRupioAdditionalInfo"]
            image_url = info["completionInfo"]["customerSpecificInfo"]["url"]
            parts = image_url.rstrip("/").split("/")
            if len(parts) < 2:
                raise RuntimeError(f"Unexpected Blogger image URL: {image_url}")
            return "/".join(parts[:-1]) + "/s0/" + parts[-1]
        except Exception as exc:
            last_error = exc
            if attempt < 5:
                import time
                time.sleep(attempt)
    raise BloggerPublishError(f"Blogger image upload failed after retries: {last_error}")

def blog_id(svc, blog_url: str) -> str:
    explicit = os.getenv("BLOGGER_BLOG_ID", "").strip()
    if explicit:
        return explicit

    # The generated googleapiclient client may not expose the Blogger blogs
    # resource in some runner environments. Resolve the ID through the v3 REST
    # endpoint directly with the same authorized OAuth token.
    creds = _credentials()
    url = "https://www.googleapis.com/blogger/v3/blogs/byurl"
    params = {"url": blog_url or DEFAULT_BLOG_URL}
    try:
        response = requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=30,
        )
        if response.status_code == 401 and creds.refresh_token:
            creds.refresh(Request())
            response = requests.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=30,
            )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise BloggerPublishError(f"Could not resolve Blogger blog ID: {exc}") from exc

    value = str(data.get("id", "")).strip()
    if not value:
        raise BloggerPublishError("Blogger REST API returned no blog ID.")
    return value

def _suggest(q: str) -> list[str]:
    try:
        r = requests.get(SUGGEST_URL, params={"client":"firefox","q":q,"hl":"ar","gl":"eg"}, headers={"User-Agent":"Mozilla/5.0"}, timeout=12)
        r.raise_for_status(); p = r.json()
        return [_clean(x) for x in (p[1] if isinstance(p,list) and len(p)>1 else []) if _clean(x)]
    except Exception as exc:
        print(f"Google Suggest unavailable for {q!r}: {exc}"); return []

def build_search_title(topic: str) -> tuple[str,str,list[str]]:
    topic = _clean(topic)
    if not topic: return "معلومة قانونية مهمة", "", []
    all_items=[]
    for q in [topic, f"{topic} قانون", f"{topic} مصر", f"ماذا أفعل إذا {topic}"]: all_items += _suggest(q)
    core=set(re.findall(r"[\u0600-\u06ff\w]+",topic.lower())); unique=[]; seen=set()
    for x in all_items:
        k=x.casefold()
        if k in seen or not 18 <= len(x) <= 105: continue
        seen.add(k); words=set(re.findall(r"[\u0600-\u06ff\w]+",x.lower()))
        if core & words or any(t in x for t in ("قانون","حقوق","عقد","محكمة","دعوى","إيجار","عمل")): unique.append(x)
    if unique:
        unique.sort(key=lambda x:(0 if "؟" in x else 1,-len(core & set(re.findall(r"[\u0600-\u06ff\w]+",x.lower()))),abs(len(x)-62)))
        return unique[0], unique[0], unique[:12]
    return (topic.rstrip("؟?.!،:")+"؟ أهم التفاصيل القانونية")[:110], "", []

def _seo_title(value: str, fallback: str = "معلومة قانونية مهمة") -> str:
    """Keep Blogger post titles concise for search snippets without cutting a word in half."""
    text = _clean(value) or _clean(fallback)
    if len(text) <= 60:
        return text
    cut = text[:60]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0].strip()
    return cut.rstrip("؟?.!،:؛-") or text[:60].strip()


def _tags(topic: str) -> list[str]:
    toks=[x for x in re.findall(r"[\u0600-\u06ff\w]+",_clean(topic)) if len(x)>2]
    return list(dict.fromkeys(["#قانون_مصر","#اسأل_محمود"]+["#"+x for x in toks[:4]]))[:6]

def _footer(topic: str) -> str:
    tags=" ".join(_tags(topic))
    return f'''<section style="margin-top:32px;padding:24px;border:1px solid #ddd;border-radius:12px"><h2>محتاج تعرف موقفك القانوني بشكل عملي؟</h2><p>لو عندك واقعة حقيقية، عقد، مشكلة أو إجراء قانوني، ابعت التفاصيل وخلّي تقييم الموقف القانوني يسبق الخطوة.</p><p><strong>للتواصل المباشر:</strong><br><a href="{WHATSAPP_URL}" target="_blank" rel="noopener">واتساب: +20 102 271 8375</a><br><a href="{FACEBOOK_URL}" target="_blank" rel="noopener">صفحة اسأل محمود على فيسبوك</a><br><a href="{LINKEDIN_URL}" target="_blank" rel="noopener">لينكدإن: محمود خيرت</a><br><a href="{BLOGGER_URL}" target="_blank" rel="noopener">مدونة اسأل محمود</a></p><p>المعلومة للتوعية العامة؛ تقييم الحالة الفعلية يعتمد على الوقائع والمستندات والاختصاص القانوني.</p><p>{html.escape(tags)}</p></section>'''

def _related(svc, bid: str, topic: str) -> list[dict[str,str]]:
    """Find a few genuinely related published posts for internal linking."""
    terms = [x for x in re.findall(r"[\u0600-\u06ff\w]+", _clean(topic)) if len(x) > 3][:5]
    seen: set[str] = set()
    found: list[dict[str,str]] = []
    for term in terms:
        try:
            data = svc.posts().search(
                blogId=bid,
                q=term,
                orderBy="PUBLISHED",
                fetchBodies=False,
            ).execute()
        except Exception as exc:
            print(f"Related-post search unavailable for {term!r}: {exc}")
            continue
        for item in data.get("items", []) or []:
            title = _clean(item.get("title"))
            url = _clean(item.get("url"))
            if not title or not url or url in seen:
                continue
            seen.add(url)
            found.append({"title": title, "url": url})
            if len(found) >= 4:
                return found
    return found



def _paragraph_html(text: str) -> str:
    return "".join(f"<p>{html.escape(part.strip())}</p>" for part in re.split(r"\n\s*\n+", str(text or "").strip()) if part.strip())


def build_article_html(title: str, topic: str, post: str, image_url: str, legal_sources: str, related: list[dict[str,str]], article: dict[str, Any] | None = None) -> str:
    article = article or {}
    meta_description = str(article.get("meta_description", "")).strip()
    lead = str(article.get("lead", "")).strip() or post
    sections = article.get("sections") if isinstance(article.get("sections"), list) else []
    faq = article.get("faq") if isinstance(article.get("faq"), list) else []
    keywords = [str(x).strip() for x in article.get("keywords", []) if str(x).strip()] if isinstance(article.get("keywords"), list) else []

    img = ""
    if image_url:
        alt_text = _clean(title)[:140]
        img = f'<figure><img src="{html.escape(image_url, quote=True)}" alt="{html.escape(alt_text, quote=True)}" title="{html.escape(alt_text, quote=True)}" loading="eager" decoding="async" style="width:100%;height:auto;border-radius:12px"></figure>'

    sections_html = "".join(
        f'<section><h2>{html.escape(str(item.get("heading", "")))}</h2>{_paragraph_html(str(item.get("body", "")))}</section>'
        for item in sections if isinstance(item, dict) and str(item.get("heading", "")).strip() and str(item.get("body", "")).strip()
    )
    faq_html = ""
    if faq:
        faq_html = '<section><h2>أسئلة شائعة</h2>' + "".join(
            f'<div><h3>{html.escape(str(item.get("question", "")))}</h3>{_paragraph_html(str(item.get("answer", "")))}</div>'
            for item in faq if isinstance(item, dict) and str(item.get("question", "")).strip() and str(item.get("answer", "")).strip()
        ) + "</section>"

    now_iso = datetime.now(timezone.utc).isoformat()
    author_url = f"{DEFAULT_BLOG_URL.rstrip('/')}/p/about-us.html"
    graph = [
        {"@type":"BlogPosting","headline":title,"description":meta_description or lead[:180],"image":[image_url] if image_url else [],"datePublished":now_iso,"dateModified":now_iso,"author":{"@type":"Person","name":"محمود خيرت","url":author_url,"sameAs":[LINKEDIN_URL,FACEBOOK_URL]},"publisher":{"@type":"Person","name":"محمود خيرت","url":author_url},"keywords":keywords or _tags(topic)},
        {"@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"اسأل محمود","item":DEFAULT_BLOG_URL},{"@type":"ListItem","position":2,"name":title}]}
    ]
    if faq:
        faq_entities = [
            {
                "@type": "Question",
                "name": str(x.get("question")),
                "acceptedAnswer": {"@type": "Answer", "text": str(x.get("answer"))},
            }
            for x in faq
            if isinstance(x, dict) and x.get("question") and x.get("answer")
        ]
        if faq_entities:
            graph.append({"@type": "FAQPage", "mainEntity": faq_entities})
    # JSON-LD is inside a script element; HTML-escaping the JSON can break parsers.
    schema = json.dumps({"@context":"https://schema.org","@graph":graph}, ensure_ascii=False).replace("</script>", "<\\/script>")

    rel = "".join(f'<li><a href="{html.escape(item["url"], quote=True)}">{html.escape(item["title"])}</a></li>' for item in related)
    related_html = f'<section><h2>اقرأ أيضًا</h2><ul>{rel}</ul></section>' if rel else ""
    byline = f'<p class="article-byline">بقلم <a href="{html.escape(author_url, quote=True)}">محمود خيرت</a> — مستشار قانوني للشركات</p>'
    sources_html = ""
    if legal_sources and _clean(legal_sources):
        source_text = str(legal_sources).strip()
        if "LEGAL RESEARCH PACKET" in source_text:
            # Research instructions and retrieval notes are internal metadata,
            # not article copy. Render only retrieved, explicitly linked sources.
            source_items = []
            for block in re.split(r"(?m)^SOURCE\s+\d+\s*$", source_text):
                url_match = re.search(r"(?m)^URL:\s*(https?://\S+)", block)
                if not url_match:
                    continue
                source_url = url_match.group(1).strip()
                title_match = re.search(r"(?m)^Title:\s*(.+)$", block)
                court_match = re.search(r"(?m)^Court/source:\s*(.+)$", block)
                case_match = re.search(r"(?m)^Case number:\s*(.+)$", block)
                date_match = re.search(r"(?m)^Date:\s*(.+)$", block)
                source_title = _clean(title_match.group(1)) if title_match else source_url
                details = []
                if court_match and _clean(court_match.group(1)) not in {"", "N/A"}:
                    details.append(_clean(court_match.group(1)))
                if case_match and _clean(case_match.group(1)) not in {"", "N/A"}:
                    details.append("رقم القضية: " + _clean(case_match.group(1)))
                if date_match and _clean(date_match.group(1)) not in {"", "N/A", "not stated"}:
                    details.append("التاريخ: " + _clean(date_match.group(1)))
                detail_html = f"<small>{html.escape(' — '.join(details))}</small>" if details else ""
                source_items.append(
                    f'<li><a href="{html.escape(source_url, quote=True)}" target="_blank" rel="noopener">{html.escape(source_title)}</a>{detail_html}</li>'
                )
            if source_items:
                sources_html = '<section><h2>المصادر القانونية</h2><ul>' + "".join(source_items) + "</ul></section>"
        else:
            sources_html = f'<section><h2>المصادر القانونية</h2>{_paragraph_html(source_text)}</section>'
    return f'<article class="khyrat-legal-article"><script type="application/ld+json">{schema}</script>{img}{byline}<section class="answer-first"><h2>الإجابة المختصرة</h2>{_paragraph_html(lead)}</section>{sections_html}{faq_html}{sources_html}{related_html}{_footer(topic)}</article>'

def _fallback_article(topic: str, post: str, legal_sources: str) -> dict[str, Any]:
    """Independent Blogger article; spreadsheet title/angle labels never become article copy."""
    body = _strip_editorial_metadata(_clean(post))
    source_text = _strip_editorial_metadata(_clean(legal_sources))
    sentences = [x.strip() for x in re.split(r"(?<=[؟!])\s+|(?<=[.،])\s+", body) if x.strip()]
    evidence = " ".join(sentences[:5]).strip() or body
    # Do not reuse the Sheet topic/title verbatim. The title is built from the
    # reader's legal question and the underlying content.
    title = "ما الذي يجب مراجعته قبل اتخاذ أي إجراء قانوني؟"
    if "عقد" in body:
        title = "قبل توقيع أي عقد: نقاط قانونية يجب مراجعتها"
    elif "إنذار" in body or "إخطار" in body:
        title = "قبل إرسال أو استلام إنذار قانوني: ما الذي يجب مراجعته؟"
    elif "إيجار" in body:
        title = "مشكلات الإيجار: ما الذي يجب مراجعته قبل اتخاذ إجراء؟"
    elif "عمل" in body or "موظف" in body:
        title = "في مسائل العمل: ما الذي يجب مراجعته قبل اتخاذ القرار؟"
    elif "شيك" in body or "أمانة" in body:
        title = "في الشيكات وإيصالات الأمانة: ما الذي يجب مراجعته قانونيًا؟"
    article = {
        "title": title,
        "meta_description": "شرح قانوني عملي يوضح ما الذي يجب مراجعته في الوقائع والمستندات والإجراءات قبل اتخاذ قرار قانوني",
        "excerpt": "دليل عملي يركز على الوقائع والمستندات والخطوات التي قد تؤثر في التقييم القانوني",
        "lead": f"قبل اتخاذ أي خطوة قانونية، المهم ليس اسم المشكلة وحده، وإنما ما حدث فعليًا وما يثبته من مستندات ومراسلات وإجراءات. {evidence}",
        "sections": [
            {"heading": "متى تبدأ المشكلة القانونية فعليًا؟", "body": evidence},
            {"heading": "ما الوقائع التي تغيّر الموقف القانوني؟", "body": f"راجع التسلسل الزمني للوقائع، وصفة كل طرف، وما تم الاتفاق عليه أو إبلاغه أو تنفيذه. {body}"},
            {"heading": "ما المستندات التي يجب مراجعتها؟", "body": "اجمع العقود والمراسلات والإيصالات والإخطارات وأي مستند يثبت الواقعة، ثم رتبها زمنيًا. دلالة المستند تعتمد على مضمونه وتاريخه وعلاقته المباشرة بالواقعة."},
            {"heading": "ما الأخطاء التي يجب تجنبها؟", "body": "تجنب اتخاذ إجراء قبل مراجعة المستندات، أو الاعتماد على قاعدة عامة دون التأكد من انطباقها، أو تجاهل المواعيد والإخطارات والإجراءات اللازمة."},
            {"heading": "كيف تتعامل مع الموقف قبل اتخاذ القرار؟", "body": f"ابدأ بتثبيت الوقائع، ثم حصر المستندات، ثم تحديد الإجراء المقترح وآثاره المحتملة، وبعد ذلك راجع القواعد القانونية المنطبقة. {('المصادر القانونية المتاحة للمحتوى: ' + source_text) if source_text else ''}"},
        ],
        "faq": [
            {"question": "هل يكفي وصف المشكلة وحده لتحديد الموقف القانوني؟", "answer": "لا، لأن التقييم يعتمد على الوقائع والمستندات والصفة والإجراءات التي تمت بالفعل."},
            {"question": "ما أول شيء يجب مراجعته قبل اتخاذ إجراء؟", "answer": "ابدأ بالوقائع الثابتة والمستندات والتسلسل الزمني وأي إخطارات أو إجراءات سابقة."},
            {"question": "هل القاعدة القانونية العامة تنطبق على كل الحالات المتشابهة؟", "answer": "ليس بالضرورة؛ الفروق في الوقائع والمستندات والصفة القانونية قد تؤثر في النتيجة."},
        ],
        "keywords": ["قانون مصر", "حقوق قانونية", "إجراءات قانونية", "مستندات قانونية"],
    }
    return _article_copy(article)

def _canonical_blog_content(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text


def cleanup_duplicate_blogger_posts(svc, bid: str) -> int:
    """Delete exact duplicate automation posts, keeping the newest copy."""
    all_items = []
    token = None
    while True:
        kwargs = {"blogId": bid, "maxResults": 500, "fetchBodies": True, "fetchImages": True}
        if token:
            kwargs["pageToken"] = token
        data = svc.posts().list(**kwargs).execute()
        all_items.extend(data.get("items", []) or [])
        token = data.get("nextPageToken")
        if not token:
            break
    groups = {}
    for item in all_items:
        title = _canonical_blog_content(item.get("title", ""))
        body = _canonical_blog_content(item.get("content", ""))
        if not title and not body:
            continue
        key = hashlib.sha256((title + "\n" + body).encode("utf-8")).hexdigest()
        groups.setdefault(key, []).append(item)
    deleted = 0
    for items in groups.values():
        if len(items) < 2:
            continue
        items.sort(key=lambda x: str(x.get("published", "")), reverse=True)
        keep = items[0]
        for duplicate in items[1:]:
            pid = _clean(duplicate.get("id"))
            if not pid or pid == _clean(keep.get("id")):
                continue
            try:
                svc.posts().delete(blogId=bid, postId=pid).execute()
                deleted += 1
                print(f"Blogger duplicate cleanup: deleted post {pid}; kept {_clean(keep.get("id"))}")
            except Exception as exc:
                print(f"Blogger duplicate cleanup: could not delete {pid}: {exc}")
    if deleted:
        print(f"Blogger duplicate cleanup removed {deleted} exact duplicate post(s).")
    else:
        print("Blogger duplicate cleanup: no exact duplicate posts found.")
    return deleted

def publish_article(*,topic:str,post:str,image_url:str="",image_path:str="",legal_sources:str="",labels:list[str]|None=None,output_dir:str="generated/blogger") -> dict[str,str]:
    svc=service(); bid=blog_id(svc,os.getenv("BLOGGER_URL",DEFAULT_BLOG_URL).strip())
    cleanup_duplicate_blogger_posts(svc, bid)
    if image_path:
        image_url = upload_blogger_image(image_path)
        print(f"Blogger image uploaded to native storage: {image_url}")
    title,search_query,candidates=build_search_title(post)
    article = None
    try:
        article = prepare_article(
            api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            model=os.getenv("GEMINI_MODEL", "").strip() or os.getenv("GEMINI_FALLBACK_MODEL", "").strip(),
            topic=topic,
            post=post,
            legal_sources=legal_sources,
        )
        title = _seo_title(str(article.get("title") or title), fallback=title)
        search_query = title
        candidates = list(dict.fromkeys([title, *[str(x).strip() for x in article.get("keywords", []) if str(x).strip()]]))[:12]
    except Exception as exc:
        print(f"Blogger editorial layer unavailable; using structured article fallback: {exc}")
        article = _fallback_article(topic, post, legal_sources)
        title = str(article.get("title") or title).strip()[:110]
        search_query = title
        candidates = list(dict.fromkeys([title, *[str(x).strip() for x in article.get("keywords", []) if str(x).strip()]]))[:12]
    article = _article_copy(article or {})
    title = str(article.get("title") or title).strip()[:110]
    content=build_article_html(title,topic,post,image_url,legal_sources,_related(svc,bid,topic),article=article)
    keyword_labels = [str(x).strip() for x in (article.get("keywords", []) if isinstance(article.get("keywords"), list) else []) if str(x).strip()]
    labs=list(dict.fromkeys([*(labels or []),"قانون مصر","اسأل محمود",*keyword_labels]))[:10]
    body={"title":title,"content":content,"labels":labs,"readerComments":"allow"}
    try: result=svc.posts().insert(blogId=bid,body=body,isDraft=False,fetchBody=True).execute()
    except Exception as exc: raise BloggerPublishError(f"Blogger publish failed: {exc}") from exc
    pid=_clean(result.get("id")); url=_clean(result.get("url"))
    if not pid or not url: raise BloggerPublishError("Blogger returned incomplete post data.")
    target=Path(output_dir); target.mkdir(parents=True,exist_ok=True); base=_safe_filename(title)
    (target/f"{base}.html").write_text(content,encoding="utf-8")
    (target/f"{base}.txt").write_text(f"{title}\n\n{re.sub(r'<[^>]+>','',content)}\n",encoding="utf-8")
    (target/f"{base}.json").write_text(json.dumps({"title":title,"search_query":search_query,"meta_description":str(article.get("meta_description", "")).strip()[:180],"post_url":url,"post_id":pid,"topic":topic,"image_url":image_url,"labels":labs},ensure_ascii=False,indent=2),encoding="utf-8")
    return {"blog_id":bid,"post_id":pid,"post_url":url,"title":title,"search_query":search_query,"search_candidates":json.dumps(candidates,ensure_ascii=False),"meta_description":str(article.get("meta_description", "")).strip()[:180]}
