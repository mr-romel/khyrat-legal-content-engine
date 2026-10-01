from __future__ import annotations

import html, json, os, re
from pathlib import Path
from typing import Any

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

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

def build_article_html(title: str, topic: str, post: str, image_url: str, legal_sources: str, related: list[dict[str,str]]) -> str:
    paras="\n".join(f"<p>{html.escape(p).replace(chr(10),'<br>')}</p>" for p in re.split(r"\n\s*\n+",str(post or "").strip()) if p.strip())
    img=f'<figure><img src="{html.escape(image_url,quote=True)}" alt="{html.escape(title,quote=True)}" loading="eager" style="width:100%;height:auto;border-radius:12px"></figure>' if image_url else ""
    rel="".join(f'<li><a href="{html.escape(x["url"],quote=True)}">{html.escape(x["title"])}</a></li>' for x in related)
    source=f"<section><h2>المصادر والإطار القانوني</h2><p>{html.escape(legal_sources)}</p></section>" if legal_sources else ""
    meta={"@context":"https://schema.org","@type":"BlogPosting","headline":title,"image":[image_url] if image_url else [],"author":{"@type":"Person","name":"محمود خيرت","url":LINKEDIN_URL},"publisher":{"@type":"Person","name":"محمود خيرت"},"keywords":_tags(topic)}
    schema=html.escape(json.dumps(meta,ensure_ascii=False))
    related_html=f"<section><h2>اقرأ أيضًا</h2><ul>{rel}</ul></section>" if rel else ""
    return f'<article><script type="application/ld+json">{schema}</script>{img}<p><strong>{html.escape(title)}</strong></p>{paras}{source}{related_html}{_footer(topic)}</article>'

def publish_article(*,topic:str,post:str,image_url:str="",legal_sources:str="",labels:list[str]|None=None,output_dir:str="generated/blogger") -> dict[str,str]:
    svc=service(); bid=blog_id(svc,os.getenv("BLOGGER_URL",DEFAULT_BLOG_URL).strip())
    title,search_query,candidates=build_search_title(topic)
    content=build_article_html(title,topic,post,image_url,legal_sources,_related(svc,bid,topic))
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
