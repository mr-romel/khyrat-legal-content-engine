from __future__ import annotations

import json
from html import escape
from pathlib import Path

from marketplace_mvp import DASHBOARD_FILE, load_state, build_offer

ROOT = Path(__file__).resolve().parents[2]


def render(state: dict) -> str:
    services = state.get("services", [])
    opportunities = state.get("opportunities", [])
    portfolio = state.get("portfolio", [])
    snapshot = json.dumps({"services": services, "opportunities": opportunities, "portfolio": portfolio}, ensure_ascii=False).replace("</", "<\\/")

    def card(item: dict, kind: str) -> str:
        iid = escape(str(item.get("id", "")), quote=True)
        title = escape(item.get("title", ""))
        status = escape(item.get("status", "DRAFT"))
        desc = escape(item.get("description", item.get("summary", "")))
        offer = escape(item.get("offer", ""))
        link = escape(item.get("source_url", ""), quote=True)
        match = int(item.get("match_score", item.get("discovery_score", 0)) or 0)
        actions = f'''<button onclick="transition('{iid}','READY_FOR_REVIEW')">مراجعة</button>
        <button onclick="transition('{iid}','APPROVED')">اعتماد</button>
        <button onclick="transition('{iid}','REJECTED')">رفض</button>'''
        if kind == "opportunity":
            actions += f'''<button onclick="copyOffer('{iid}')">نسخ العرض</button>
            <button onclick="regenerate('{iid}')">إعادة توليد العرض</button>'''
            if link:
                actions += f'''<a class="btn" href="{link}" target="_blank" rel="noopener">فتح المشروع على مستقل</a>'''
        return f'''<article class="item" data-id="{iid}" data-search="{title} {desc} {status}">
        <div class="row"><strong>{title}</strong><span class="badge">{status}</span></div>
        <p>{desc}</p>
        {f'<div class="score">{match}% Match</div>' if kind == "opportunity" else ''}
        {f'<details open><summary>العرض</summary><textarea id="offer-{iid}">{offer}</textarea></details>' if kind == "opportunity" else ''}
        <div class="actions">{actions}</div></article>'''

    service_html = "".join(card(x, "service") for x in services) or '<div class="item">لا توجد خدمات.</div>'
    opp_html = "".join(card(x, "opportunity") for x in opportunities) or '<div class="item">لا توجد فرص.</div>'
    portfolio_html = "".join(f'<article class="item"><strong>{escape(x.get("title", ""))}</strong><p>{escape(x.get("summary", ""))}</p></article>' for x in portfolio)

    return f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-store"><title>Khyrat Marketplace Dashboard</title>
<style>body{{font-family:Arial,Tahoma,sans-serif;background:#f4f6f8;color:#20242a;margin:0}}.wrap{{max-width:1180px;margin:auto;padding:18px}}header,section,.item{{background:#fff;border:1px solid #dfe3e8;border-radius:14px;padding:16px;margin:12px 0}}.grid,.items{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.grid{{grid-template-columns:repeat(4,1fr)}}.stat{{padding:14px;background:#f8fafc;border-radius:10px}}.stat b{{display:block;font-size:25px;margin-top:5px}}.row{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}}.badge,.score{{display:inline-block;background:#eef2f6;border-radius:999px;padding:5px 9px;font-size:12px}}.actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}}button,.btn{{padding:8px 12px;border:1px solid #ccd2d8;border-radius:8px;background:#f2f3f5;cursor:pointer;text-decoration:none;color:inherit;font-size:14px}}textarea,input{{width:100%;box-sizing:border-box;border:1px solid #ccd2d8;border-radius:8px;padding:10px;margin-top:7px}}textarea{{min-height:130px}}.muted{{color:#69717d}}#msg{{position:fixed;bottom:18px;left:18px;background:#20242a;color:#fff;padding:10px 14px;border-radius:10px;display:none}}@media(max-width:800px){{.grid,.items{{grid-template-columns:1fr}}}}</style></head><body><div class="wrap">
<header><h1>Khyrat Marketplace Dashboard</h1><p class="muted">مراجعة → اعتماد → تجهيز التنفيذ اليدوي. الحالة تحفظ على هذا الجهاز.</p><input id="search" placeholder="بحث..." oninput="filterCards()"><button onclick="resetLocal()">إعادة تحميل الحالة الأصلية</button></header>
<div class="grid"><div class="stat">خدمات<b id="servicesCount">{len(services)}</b></div><div class="stat">فرص مستقل<b id="oppCount">{len(opportunities)}</b></div><div class="stat">بانتظار المراجعة<b id="reviewCount">0</b></div><div class="stat">معتمدة<b id="approvedCount">0</b></div></div>
<section><h2>فرص مستقل + العروض</h2><div id="opportunities" class="items">{opp_html}</div></section>
<section><h2>خدمات خمسات</h2><div class="items">{service_html}</div></section>
<section><h2>Portfolio</h2><div class="items">{portfolio_html or '<div class="item">لا توجد أعمال.</div>'}</div></section>
<section><h2>ملاحظة تشغيل</h2><p>هذه نسخة GitHub Pages تعمل بدون سيرفر. أزرار المراجعة والاعتماد والرفض والنسخ وفتح المشروع تعمل محليًا، ولا تسجل دخولًا أو تقدم عروضًا تلقائيًا على مستقل أو خمسات.</p></section></div><div id="msg"></div>
<script>const ORIGINAL={snapshot};let state=JSON.parse(localStorage.getItem('khyrat_marketplace_state')||'null')||ORIGINAL;
function save(){{localStorage.setItem('khyrat_marketplace_state',JSON.stringify(state));render()}}
function find(id){{return [...state.opportunities,...state.services].find(x=>x.id===id)}}
function transition(id,status){{const x=find(id);if(!x)return; x.status=status; x.lifecycle=status; show('تم تغيير الحالة إلى '+status);save()}}
function regenerate(id){{const x=find(id);if(!x)return; const days=x.suggested_days||2, price=x.suggested_price_egp||1500; x.offer='أهلًا، اطلعت على طلبك، وأقدر أساعدك في المراجعة القانونية للمستند وتحليل البنود التي قد تسبب لك مخاطر أو التزامات غير واضحة.\\n\\nهراجع المستند بندًا بندًا، وأوضح أي نقاط تحتاج تعديل أو إعادة صياغة، مع تقديم البديل المقترح بشكل عملي وواضح.\\n\\nأقدر أبدأ فورًا، والمدة المتوقعة '+days+' أيام، والميزانية '+price+' جنيه مصري.';x.status='OFFER_READY';show('تم إعادة توليد العرض');save()}}
async function copyOffer(id){{const x=find(id);if(!x)return;try{{await navigator.clipboard.writeText(x.offer||'');show('تم نسخ العرض')}}catch(e){{const el=document.getElementById('offer-'+id);el.focus();el.select();document.execCommand('copy');show('تم نسخ العرض')}}}}
function filterCards(){{const q=document.getElementById('search').value.toLowerCase().trim();document.querySelectorAll('.item[data-search]').forEach(x=>x.style.display=x.dataset.search.toLowerCase().includes(q)?'block':'none')}}
function resetLocal(){{localStorage.removeItem('khyrat_marketplace_state');location.reload()}}
function render(){{location.reload()}}
function show(t){{const m=document.getElementById('msg');m.textContent=t;m.style.display='block';setTimeout(()=>m.style.display='none',1800)}}
const r=Object.values(state.opportunities).filter(x=>['READY_FOR_REVIEW','OFFER_READY'].includes(x.status)).length;const a=Object.values(state.opportunities).filter(x=>['APPROVED','SUBMITTED','WON'].includes(x.status)).length;document.getElementById('reviewCount').textContent=r;document.getElementById('approvedCount').textContent=a;
</script></body></html>'''


def main() -> None:
    state = load_state()
    DASHBOARD_FILE.write_text(render(state), encoding="utf-8")
    print(DASHBOARD_FILE)


if __name__ == "__main__":
    main()
