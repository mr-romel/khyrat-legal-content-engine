from __future__ import annotations
import hashlib, html, json, os, re, unicodedata
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from blogger_publisher import DEFAULT_BLOG_URL, blog_id, service

class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in {"script","style","noscript"}: self.skip+=1
    def handle_endtag(self, tag):
        if tag in {"script","style","noscript"} and self.skip: self.skip-=1
    def handle_data(self, data):
        if not self.skip and data.strip(): self.parts.append(data.strip())

def normalize(s):
    p=Text(); p.feed(s or "")
    s=html.unescape(" ".join(p.parts))
    s=unicodedata.normalize("NFKC",s)
    s=re.sub(r"[\u064B-\u065F\u0670\u0640]","",s).casefold()
    s=re.sub(r"https?://\S+"," ",s)
    s=re.sub(r"[^\w\u0600-\u06FF]+"," ",s)
    return " ".join(s.split())

def fingerprint(post):
    body=normalize(str(post.get("content","")))
    return hashlib.sha256(body.encode()).hexdigest() if len(body)>=500 else ""

def date_key(p):
    d=str(p.get("published") or p.get("updated") or "9999")
    try: d=datetime.fromisoformat(d.replace("Z","+00:00")).isoformat()
    except ValueError: d="9999"
    return d,str(p.get("id",""))

def main():
    svc=service(); bid=blog_id(svc,os.getenv("BLOGGER_URL",DEFAULT_BLOG_URL).strip())
    posts=[]; token=None
    while True:
        args={"blogId":bid,"status":"LIVE","fetchBodies":True,"maxResults":500}
        if token: args["pageToken"]=token
        data=svc.posts().list(**args).execute()
        posts.extend(data.get("items",[])); token=data.get("nextPageToken")
        if not token: break
    groups={}
    for p in posts:
        fp=fingerprint(p)
        if fp: groups.setdefault(fp,[]).append(p)
    candidates=[]
    for fp,group in groups.items():
        if len(group)>1:
            ordered=sorted(group,key=date_key); keep=ordered[0]
            for p in ordered[1:]:
                candidates.append({"fingerprint":fp,"keep_id":str(keep["id"]),"keep_title":keep.get("title",""),"keep_url":keep.get("url",""),"duplicate_id":str(p["id"]),"duplicate_title":p.get("title",""),"duplicate_url":p.get("url","")})
    apply=os.getenv("BLOGGER_DEDUP_APPLY","false").lower()=="true"
    report={"live_posts_scanned":len(posts),"exact_duplicate_groups":sum(len(g)>1 for g in groups.values()),"candidates":candidates,"deleted":[],"errors":[],"mode":"APPLY" if apply else "DRY_RUN","policy":"Only exact normalized body duplicates of at least 500 characters; keep oldest; near-duplicates are never automatically deleted."}
    for item in candidates:
        if not apply:
            print("DRY_RUN_DUPLICATE",item["duplicate_id"],"KEEP",item["keep_id"]); continue
        try:
            a=svc.posts().get(blogId=bid,postId=item["keep_id"],fetchBody=True).execute()
            b=svc.posts().get(blogId=bid,postId=item["duplicate_id"],fetchBody=True).execute()
            if fingerprint(a)!=item["fingerprint"] or fingerprint(b)!=item["fingerprint"]: raise RuntimeError("Content changed since scan; deletion cancelled")
            svc.posts().delete(blogId=bid,postId=item["duplicate_id"]).execute()
            report["deleted"].append(item); print("DELETED_EXACT_DUPLICATE",item["duplicate_id"],"KEPT",item["keep_id"])
        except Exception as e:
            report["errors"].append({"id":item["duplicate_id"],"error":str(e)[:400]}); print("DELETE_FAILED",item["duplicate_id"],e)
    path=Path(os.getenv("BLOGGER_DEDUP_REPORT","data/blogger_dedup_report.json")); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("SUMMARY",json.dumps({"scanned":len(posts),"candidates":len(candidates),"deleted":len(report["deleted"]),"errors":len(report["errors"]),"mode":report["mode"]},ensure_ascii=False))
    return 1 if report["errors"] else 0
if __name__=="__main__": raise SystemExit(main())
