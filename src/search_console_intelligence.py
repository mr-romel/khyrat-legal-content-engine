from __future__ import annotations
import os
from datetime import date, timedelta
from typing import Any
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import _service_account_info, _sheet_id
from sheets import _ensure_sheet, _append, get_values

SEARCH_CONSOLE_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
SEARCH_HEADERS = ["Captured At","Query","Page","Clicks","Impressions","CTR","Position","Intent","Opportunity","Source"]
KEYWORD_HEADERS = ["Keyword","Page","Clicks","Impressions","CTR","Position","Intent","Keyword Type","Coverage","Opportunity Score","Action","Related Questions","Last Seen"]
OPPORTUNITY_HEADERS = ["Opportunity ID","Keyword","Page","Type","Score","Reason","Recommended Action","Status","Created At"]
REFRESH_HEADERS = ["Page","Keyword","Position","Impressions","CTR","Reason","Recommended Action","Status","Updated At"]
MONETIZATION_HEADERS = ["Keyword","Service","Intent","CTA Rule","Conversion Action","Status"]

def _service():
    creds = Credentials.from_service_account_info(_service_account_info(), scopes=[SEARCH_CONSOLE_SCOPE])
    return build("searchconsole","v1",credentials=creds,cache_discovery=False)

def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

def _site_url() -> str:
    return os.getenv("SEARCH_CONSOLE_SITE_URL","").strip()

def _intent(query: str) -> str:
    q=query.casefold()
    if any(x in q for x in ("ازاي","إزاي","كيف","ماذا أفعل","اعمل ايه","أعمل إيه")): return "HOW_TO"
    if any(x in q for x in ("هل ","هل يجوز","ينفع","ما هو","ما هي","متى","لماذا")): return "QUESTION"
    if any(x in q for x in ("سعر","تكلفة","محامي","استشارة","صياغة","مراجعة عقد")): return "COMMERCIAL"
    return "INFORMATIONAL"

def _score(clicks: float, impressions: float, ctr: float, position: float) -> float:
    demand=min(impressions/1000.0,1.0)*35
    click_signal=min(clicks/100.0,1.0)*15
    ctr_gap=max(0.0,min(1.0,0.08-ctr))/0.08*20
    position_window=25 if 5 <= position <= 20 else 10 if position < 30 else 0
    return round(min(100.0,demand+click_signal+ctr_gap+position_window),2)

def query_search_console(days: int=28,row_limit: int=25000) -> list[dict[str,Any]]:
    site=_site_url()
    if not site: raise RuntimeError("SEARCH_CONSOLE_SITE_URL is missing.")
    end=date.today()-timedelta(days=2)
    start=end-timedelta(days=max(1,days)-1)
    response=_service().searchanalytics().query(siteUrl=site,body={
        "startDate":start.isoformat(),"endDate":end.isoformat(),
        "dimensions":["query","page"],"rowLimit":row_limit,"dataState":"final"
    }).execute()
    rows=[]
    for item in response.get("rows",[]) or []:
        keys=item.get("keys",[])
        query=_clean(keys[0] if len(keys)>0 else "")
        page=_clean(keys[1] if len(keys)>1 else "")
        if not query: continue
        clicks=float(item.get("clicks",0) or 0); impressions=float(item.get("impressions",0) or 0)
        ctr=float(item.get("ctr",0) or 0); position=float(item.get("position",0) or 0)
        rows.append({"query":query,"page":page,"clicks":clicks,"impressions":impressions,"ctr":ctr,
                     "position":position,"intent":_intent(query),"opportunity":_score(clicks,impressions,ctr,position)})
    return rows

def _related_questions(query: str) -> str:
    base=query.rstrip("؟?. ")
    return " | ".join(dict.fromkeys([base+"؟",f"ما شروط {base}؟",f"ماذا أفعل إذا {base}؟",
        f"ما المستندات المطلوبة في {base}؟",f"ما المواعيد أو الاستثناءات المرتبطة بـ {base}؟"]))

def _keyword_type(row: dict[str,Any]) -> str:
    if row["intent"]=="QUESTION" or "؟" in row["query"]: return "QUESTION"
    if row["intent"]=="HOW_TO": return "HOW_TO"
    if row["intent"]=="COMMERCIAL": return "COMMERCIAL"
    return "TOPIC"

def _action(row: dict[str,Any]) -> str:
    if 8 <= row["position"] <= 20 and row["impressions"] >= 20: return "REFRESH_EXISTING"
    if row["opportunity"] >= 55 and row["position"] > 20: return "CREATE_SUPPORTING_ARTICLE"
    if row["ctr"] < 0.03 and row["impressions"] >= 100: return "IMPROVE_TITLE_SNIPPET"
    return "MONITOR"

def build_keyword_rows(rows: list[dict[str,Any]]) -> list[list[str]]:
    return [[r["query"],r["page"],f'{r["clicks"]:.2f}',f'{r["impressions"]:.2f}',f'{r["ctr"]:.4f}',
             f'{r["position"]:.2f}',r["intent"],_keyword_type(r),"OBSERVED",f'{r["opportunity"]:.2f}',
             _action(r),_related_questions(r["query"]),date.today().isoformat()] for r in rows]

def build_opportunities(rows: list[dict[str,Any]]) -> list[list[str]]:
    output=[]
    for r in sorted(rows,key=lambda x:x["opportunity"],reverse=True)[:100]:
        action=_action(r)
        if action=="MONITOR": continue
        reason="صفحة بين 8 و20 مع طلب بحث واضح" if action=="REFRESH_EXISTING" else (
            "طلب بحث واعد يحتاج تغطية أو صفحة داعمة" if action=="CREATE_SUPPORTING_ARTICLE"
            else "انطباعات مرتفعة ونسبة نقر منخفضة")
        oid="OPP-"+str(abs(hash((r["query"],r["page"])))%10**12).zfill(12)
        output.append([oid,r["query"],r["page"],action,f'{r["opportunity"]:.2f}',reason,action,"OPEN",date.today().isoformat()])
    return output

def build_refresh_queue(rows: list[dict[str,Any]]) -> list[list[str]]:
    output=[]
    for r in rows:
        if 8 <= r["position"] <= 20 and r["impressions"] >= 20:
            output.append([r["page"],r["query"],f'{r["position"]:.2f}',f'{r["impressions"]:.2f}',f'{r["ctr"]:.4f}',
                "فرصة تحسين صفحة موجودة للوصول إلى الصفحة الأولى",
                "أضف الإجابة المباشرة + FAQ + روابط داخلية + راجع العنوان","OPEN",date.today().isoformat()])
    return output[:250]

def _monetization_rows(rows: list[dict[str,Any]]) -> list[list[str]]:
    rules=(("عقد","مراجعة وصياغة العقود","HIGH_INTENT"),
           ("شركة","خدمات الشركات","BUSINESS_INTENT"),
           ("شريك","خدمات الشركات","BUSINESS_INTENT"),
           ("موظف","استشارة قانون العمل","HIGH_INTENT"),
           ("عامل","استشارة قانون العمل","HIGH_INTENT"),
           ("فصل","استشارة قانون العمل","HIGH_INTENT"),
           ("شيك","استشارة مدنية وتجارية","LEGAL_PROBLEM"),
           ("إيصال","استشارة مدنية وتجارية","LEGAL_PROBLEM"),
           ("دين","استشارة مدنية وتجارية","LEGAL_PROBLEM"))
    out=[]; seen=set()
    for r in rows:
        q=r["query"]
        for term,service,intent in rules:
            if term in q:
                key=(q,service)
                if key not in seen:
                    out.append([q,service,intent,"محتوى مفيد أولًا؛ CTA خفيف بعد الإجابة",
                                "زيارة صفحة الخدمة أو طلب تقييم أولي","OPEN"]); seen.add(key)
                break
    return out

def write_snapshot(rows: list[dict[str,Any]], service, spreadsheet_id: str) -> None:
    for name,headers in (("SearchConsole",SEARCH_HEADERS),("KeywordMap",KEYWORD_HEADERS),
                         ("ContentOpportunities",OPPORTUNITY_HEADERS),("ContentRefreshQueue",REFRESH_HEADERS),
                         ("MonetizationMap",MONETIZATION_HEADERS)):
        _ensure_sheet(service,spreadsheet_id,name,headers)
    stamp=date.today().isoformat()
    existing=get_values(service,spreadsheet_id,"SearchConsole!A:J")
    seen={(str(r[1]).strip(),str(r[2]).strip(),str(r[0]).strip()) for r in existing[1:] if len(r)>=3}
    for r in rows:
        key=(r["query"],r["page"],stamp)
        if key not in seen:
            _append(service,spreadsheet_id,"SearchConsole",[stamp,r["query"],r["page"],f'{r["clicks"]:.2f}',
                f'{r["impressions"]:.2f}',f'{r["ctr"]:.4f}',f'{r["position"]:.2f}',r["intent"],
                f'{r["opportunity"]:.2f}',"GOOGLE_SEARCH_CONSOLE"])
    for r in build_keyword_rows(rows): _append(service,spreadsheet_id,"KeywordMap",r)
    for r in build_opportunities(rows): _append(service,spreadsheet_id,"ContentOpportunities",r)
    for r in build_refresh_queue(rows): _append(service,spreadsheet_id,"ContentRefreshQueue",r)
    for r in _monetization_rows(rows): _append(service,spreadsheet_id,"MonetizationMap",r)

def run(days: int=28) -> dict[str,int]:
    from sheets import create_service
    rows=query_search_console(days=days)
    sheet_service=create_service(_service_account_info())
    write_snapshot(rows,sheet_service,_sheet_id())
    return {"rows":len(rows),"opportunities":len(build_opportunities(rows)),"refresh_items":len(build_refresh_queue(rows)),"monetization":len(_monetization_rows(rows))}
