from __future__ import annotations
import html
import re
from typing import Any
from blogger_publisher import blog_id, service

TOKEN_RE=re.compile(r"[\u0600-\u06ffA-Za-z0-9]+")
MONETIZATION_RULES=[
    (("عقد","تعاقد","بند"),"مراجعة وصياغة العقود","HIGH_INTENT"),
    (("شركة","شريك","مدير","تأسيس"),"خدمات الشركات","BUSINESS_INTENT"),
    (("موظف","عامل","فصل","استقالة","جزاء"),"استشارة قانون العمل","HIGH_INTENT"),
    (("شيك","إيصال","دين","مطالبة"),"استشارة مدنية وتجارية","LEGAL_PROBLEM"),
]

def tokens(text:str)->set[str]:
    return {x.casefold() for x in TOKEN_RE.findall(str(text or "")) if len(x)>2}

def similarity(a:str,b:str)->float:
    aa,bb=tokens(a),tokens(b)
    return len(aa & bb)/max(1,len(aa | bb)) if aa and bb else 0.0

def monetization_map(query:str)->tuple[str,str]:
    for terms,service_name,intent in MONETIZATION_RULES:
        if any(term in str(query or "") for term in terms): return service_name,intent
    return "استشارة قانونية عامة","EDUCATIONAL"

def load_posts(svc,bid:str)->list[dict[str,str]]:
    data=svc.posts().list(blogId=bid,status="LIVE",fetchBodies=False,maxResults=500,orderBy="PUBLISHED").execute()
    return [{"id":str(x.get("id","")),"title":str(x.get("title","")).strip(),"url":str(x.get("url","")).strip()}
            for x in data.get("items",[]) or [] if str(x.get("id","")).strip() and str(x.get("title","")).strip()]

def related_topics(query:str,posts:list[dict[str,str]],limit:int=5)->list[dict[str,Any]]:
    scored=[]
    for post in posts:
        score=similarity(query,post["title"])
        if score>=0.15: scored.append((score,post))
    scored.sort(key=lambda item:item[0],reverse=True)
    return [{"title":p["title"],"url":p["url"],"score":round(s,3)} for s,p in scored[:limit]]

def build_link_block(links:list[dict[str,Any]])->str:
    items="".join('<li><a href="{0}">{1}</a></li>'.format(html.escape(x["url"],quote=True),html.escape(x["title"]))
                  for x in links if x.get("url") and x.get("title"))
    return '<section class="khyrat-related-topics"><h2>موضوعات مرتبطة بالسؤال</h2><ul>'+items+'</ul></section>' if items else ""

def inject_internal_links(content:str,links:list[dict[str,Any]])->str:
    block=build_link_block(links)
    if not block or "khyrat-related-topics" in content: return content
    return content.replace("</article>",block+"</article>",1) if "</article>" in content else content+block

def enrich_live_posts(dry_run:bool=True)->dict[str,int]:
    svc=service(); bid=blog_id(svc,""); posts=load_posts(svc,bid)
    updated=0
    for post in posts:
        related=related_topics(post["title"],[x for x in posts if x["id"]!=post["id"]],3)
        if not related or dry_run: continue
        current=svc.posts().get(blogId=bid,postId=post["id"],fetchBody=True).execute()
        content=str(current.get("content","") or "")
        enriched=inject_internal_links(content,related)
        if enriched==content: continue
        svc.posts().patch(blogId=bid,postId=post["id"],body={"content":enriched}).execute()
        updated+=1
    return {"posts":len(posts),"updated":updated}

def build_monetization_rows(keyword_rows:list[dict[str,str]])->list[list[str]]:
    rows=[]
    for row in keyword_rows:
        query=row.get("Keyword","")
        service_name,intent=monetization_map(query)
        if intent!="EDUCATIONAL":
            rows.append([query,service_name,intent,"محتوى مفيد أولًا؛ CTA خفيف بعد الإجابة",
                         "زيارة صفحة الخدمة أو طلب تقييم أولي","OPEN"])
    return rows
