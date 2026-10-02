from __future__ import annotations

import html, json, os, re
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

def blog_id(svc, blog_url: str) -> str:
    explicit = os.getenv("BLOGGER_BLOG_ID", "").strip()
    if explicit: return explicit
    try: data = svc.blogs().getByUrl(url=blog_url or DEFAULT_BLOG_URL).execute()
    except Exception as exc: raise BloggerPublishError(f"Could not resolve Blogger blog ID: {exc}") from exc
    value = str(data.get("id", "")).strip()
    if not value: raise BloggerPublishError("Blogger returned no blog ID.")
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

def _tags(topic: str) -> list[str]:
    toks=[x for x in re.findall(r"[\u0600-\u06ff\w]+",_clean(topic)) if len(x)>2]
    return list(dict.fromkeys(["#قانون_مصر","#اسأل_محمود"]+["#"+x for x in toks[:4]]))[:6]

def _footer(topic: str) -> str:
    tags=" ".join(_tags(topic))
    return f'''<section style="margin-top:32px;padding:24px;border:1px solid #ddd;border-radius:12px"><h2>محتاج تعرف موقفك القانوني بشكل عملي؟</h2><p>لو عندك واقعة حقيقية، عقد، مشكلة أو إجراء قانوني، ابعت التفاصيل وخلّي تقييم الموقف القانوني يسبق الخطوة.</p><p><strong>للتواصل المباشر:</strong><br><a href="{WHATSAPP_URL}" target="_blank" rel="noopener">واتساب: +20 102 271 8375</a><br><a href="{FACEBOOK_URL}" target="_blank" rel="noopener">صفحة اسأل محمود على فيسبوك</a><br><a href="{LINKEDIN_URL}" target="_blank" rel="noopener">لينكدإن: محمود خيرت</a><br><a href="{BLOGGER_URL}" target="_blank" rel="noopener">مدونة اسأل محمود</a></p><p>المعلومة للتوعية العامة؛ تقييم الحالة الفعلية يعتمد على الوقائع والمستندات والاختصاص القانوني.</p><p>{html.escape(tags)}</p></section>'''

def _related(svc, bid: str, topic: str) -> list[dict[str,str]]:
    try: data=svc.posts().list(blogId=bid,status="live",fetchBodies=False,maxResults=25,orderBy="PUBLISHED").execute()
    except Exception as exc: print(f"Related-post lookup unavailable: {exc}"); return []
    core=set(re.findall(r"[\u0600-\u06ff\w]+",_clean(topic).lower())); scored=[]
    for x in data.get("items",[]) or []:
        title=_clean(x.get("title")); url=_clean(x.get("url"))
        if title and url: scored.append((len(core & set(re.findall(r"[\u0600-\u06ff\w]+",title.lower()))),{"title":title,"url":url}))
    scored.sort(key=lambda z:z[0],reverse=True)
    return [x[1] for x in scored if x[0]>0][:3]

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
        img = f'<figure><img src="{html.escape(image_url, quote=True)}" alt="{html.escape(title, quote=True)}" loading="eager" decoding="async" style="width:100%;height:auto;border-radius:12px"></figure>'

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

    graph = [
        {"@type":"BlogPosting","headline":title,"description":meta_description or lead[:180],"image":[image_url] if image_url else [],"author":{"@type":"Person","name":"محمود خيرت","url":LINKEDIN_URL},"publisher":{"@type":"Person","name":"اسأل محمود"},"keywords":keywords or _tags(topic)},
        {"@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"اسأل محمود"},{"@type":"ListItem","position":2,"name":title}]}
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
    schema = html.escape(json.dumps({"@context":"https://schema.org","@graph":graph}, ensure_ascii=False))

    rel = "".join(f'<li><a href="{html.escape(item["url"], quote=True)}">{html.escape(item["title"])}</a></li>' for item in related)
    related_html = f'<section><h2>اقرأ أيضًا</h2><ul>{rel}</ul></section>' if rel else ""
    return f'<article class="khyrat-legal-article"><script type="application/ld+json">{schema}</script>{img}<section class="answer-first"><h2>الإجابة المختصرة</h2>{_paragraph_html(lead)}</section>{sections_html}{faq_html}{related_html}{_footer(topic)}</article>'

def _fallback_article(topic: str, post: str, legal_sources: str) -> dict[str, Any]:
    """Structured Blogger article fallback when the editorial LLM is unavailable."""
    clean_topic = _clean(topic)
    source_text = _clean(legal_sources)
    body = _clean(post)
    title = f"{clean_topic}: ماذا تعرف قبل اتخاذ أي إجراء قانوني؟"[:110]
    sentences = [x.strip() for x in re.split(r"(?<=[؟!])\s+|(?<=[.،])\s+", body) if x.strip()]
    evidence = " ".join(sentences[:4]).strip() or body
    article = {
        "title": title,
        "meta_description": f"شرح عملي ومبسط لموضوع {clean_topic} في السياق القانوني المصري، وما الذي يجب مراجعته قبل اتخاذ قرار أو إجراء",
        "excerpt": f"دليل عملي حول {clean_topic} يركز على الفكرة الأساسية، أثرها العملي، والوقائع والمستندات التي قد تغيّر التقييم القانوني",
        "lead": f"إذا كنت تبحث عن موقف {clean_topic}، فابدأ بالقاعدة العملية: لا يكفي اسم الموضوع وحده للحكم على الحالة، لأن النتيجة القانونية تتأثر بالوقائع والمستندات والإجراء الذي تم اتخاذه. المادة الأصلية تتناول ذلك من زاوية عملية، وهنا نعيد ترتيبها في صورة دليل يصلح للقراءة والبحث.",
        "sections": [
            {"heading": f"ما المقصود بـ {clean_topic} في التطبيق العملي؟", "body": evidence},
            {"heading": "ما الذي يغيّر التقييم القانوني؟", "body": f"في أي واقعة مرتبطة بهذا الموضوع، لا تنظر إلى الواقعة منفصلة عن المستندات والتسلسل الزمني وتصرفات الأطراف. {body}"},
            {"heading": "ما المستندات والوقائع التي يجب مراجعتها؟", "body": "راجع العقود والمراسلات والإيصالات والإخطارات وأي مستند يثبت ما حدث فعليًا، مع ترتيبها زمنيًا. وجود المستند وحده لا يحسم النتيجة دائمًا؛ المهم أيضًا مضمونه وتاريخ صدوره وعلاقته بالواقعة."},
            {"heading": "أخطاء عملية قد تضعف الموقف", "body": "من أكثر الأخطاء شيوعًا اتخاذ إجراء قبل مراجعة المستندات، أو الاعتماد على قاعدة عامة دون التأكد من انطباقها على الحالة، أو تجاهل المواعيد والإخطارات والإجراءات المطلوبة. لذلك يجب أن يسبق القرارَ المهمَّ فحصٌ للوقائع والمستندات ذات الصلة."},
            {"heading": "كيف تتعامل مع الموضوع قبل اتخاذ القرار؟", "body": f"ابدأ بتحديد الوقائع الثابتة، ثم اجمع المستندات، ثم حدّد الإجراء المقترح وآثاره المحتملة، وبعدها راجع المسألة على ضوء القواعد القانونية المنطبقة. {('المصادر القانونية المتاحة للمحتوى: ' + source_text) if source_text else 'وإذا كانت الواقعة مرتبطة بعقد أو نزاع أو إجراء قائم، فالتفاصيل الدقيقة هي التي تحدد الخطوة المناسبة.'}"},
        ],
        "faq": [
            {"question": f"هل اسم الموضوع وحده يكفي لتحديد الموقف القانوني في {clean_topic}؟", "answer": "لا، لأن التطبيق يتوقف على الوقائع والمستندات والصفة والإجراء والظروف المحيطة بالحالة"},
            {"question": f"ما الذي يجب مراجعته أولًا في مسألة {clean_topic}؟", "answer": "ابدأ بالوقائع الثابتة والمستندات والتسلسل الزمني والإخطارات أو الإجراءات التي تمت بالفعل"},
            {"question": "هل يمكن تطبيق قاعدة عامة على كل الحالات المتشابهة؟", "answer": "ليس بالضرورة، لأن الفروق في الوقائع والمستندات والصفة القانونية قد تغيّر النتيجة"},
        ],
        "keywords": [clean_topic, f"{clean_topic} في القانون المصري", f"إجراءات {clean_topic}", f"حقوق والتزامات {clean_topic}"],
    }
    return article

def publish_article(*,topic:str,post:str,image_url:str="",legal_sources:str="",labels:list[str]|None=None,output_dir:str="generated/blogger") -> dict[str,str]:
    svc=service(); bid=blog_id(svc,os.getenv("BLOGGER_URL",DEFAULT_BLOG_URL).strip())
    title,search_query,candidates=build_search_title(topic)
    article = None
    try:
        article = prepare_article(
            api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            model=os.getenv("GEMINI_MODEL", "").strip() or os.getenv("GEMINI_FALLBACK_MODEL", "").strip(),
            topic=topic,
            post=post,
            legal_sources=legal_sources,
        )
        title = str(article.get("title") or title).strip()[:110]
        search_query = title
        candidates = list(dict.fromkeys([title, *[str(x).strip() for x in article.get("keywords", []) if str(x).strip()]]))[:12]
    except Exception as exc:
        print(f"Blogger editorial layer unavailable; using structured article fallback: {exc}")
        article = _fallback_article(topic, post, legal_sources)
        title = str(article.get("title") or title).strip()[:110]
        search_query = title
        candidates = list(dict.fromkeys([title, *[str(x).strip() for x in article.get("keywords", []) if str(x).strip()]]))[:12]
    content=build_article_html(title,topic,post,image_url,legal_sources,_related(svc,bid,topic),article=article)
    labs=list(dict.fromkeys([*(labels or []),"قانون مصر","اسأل محمود"]))[:10]
    body={"title":title,"content":content,"labels":labs,"readerComments":"allow","customMetaData":json.dumps({"search_query":search_query,"search_candidates":candidates,"topic":topic,"seo_title_source":"google_suggest","brand":"Ask Mahmoud"},ensure_ascii=False)}
    try: result=svc.posts().insert(blogId=bid,body=body,isDraft=False,fetchBody=True).execute()
    except Exception as exc: raise BloggerPublishError(f"Blogger publish failed: {exc}") from exc
    pid=_clean(result.get("id")); url=_clean(result.get("url"))
    if not pid or not url: raise BloggerPublishError("Blogger returned incomplete post data.")
    target=Path(output_dir); target.mkdir(parents=True,exist_ok=True); base=_safe_filename(title)
    (target/f"{base}.html").write_text(content,encoding="utf-8")
    (target/f"{base}.txt").write_text(f"{title}\n\n{re.sub(r'<[^>]+>','',content)}\n",encoding="utf-8")
    (target/f"{base}.json").write_text(json.dumps({"title":title,"search_query":search_query,"post_url":url,"post_id":pid,"topic":topic,"image_url":image_url,"labels":labs},ensure_ascii=False,indent=2),encoding="utf-8")
    return {"blog_id":bid,"post_id":pid,"post_url":url,"title":title,"search_query":search_query,"search_candidates":json.dumps(candidates,ensure_ascii=False)}
