from __future__ import annotations

import json

from marketplace_mvp import DASHBOARD_FILE, load_state

DEFAULT_BACKEND = "https://khyrat-legal-content-engine.vercel.app"


def render(state: dict) -> str:
    snapshot = json.dumps(
        {
            "services": state.get("services", []),
            "opportunities": state.get("opportunities", []),
            "portfolio": state.get("portfolio", []),
            "activity": state.get("activity", []),
        }, ensure_ascii=False,
    ).replace("</", "<\\/")

    html = f'''<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-store"><title>خيرت — Marketplace Dashboard</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#f3f5f7;color:#20242a;font-family:Tahoma,Arial,sans-serif}}.wrap{{max-width:1250px;margin:auto;padding:18px}}header,section,.card{{background:#fff;border:1px solid #dfe3e8;border-radius:15px;padding:16px;margin:12px 0}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.items{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.stat{{background:#f8fafc;border-radius:10px;padding:13px}}.stat b{{display:block;font-size:25px;margin-top:5px}}.row{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}}.badge,.score{{background:#eef2f6;border-radius:999px;padding:5px 9px;font-size:12px;white-space:nowrap}}.muted{{color:#66717c;font-size:13px}}.actions,.toolbar{{display:flex;gap:8px;flex-wrap:wrap;margin-top:11px}}button,.open{{border:1px solid #cbd1d8;border-radius:8px;padding:9px 12px;background:#f7f8fa;color:#20242a;cursor:pointer;text-decoration:none;font:inherit}}button.primary,.open.primary{{background:#20242a;color:#fff}}button.danger{{background:#fff0f0}}input,textarea{{width:100%;padding:10px;border:1px solid #cbd1d8;border-radius:8px;margin-top:5px;font:inherit}}textarea{{min-height:150px;line-height:1.7;resize:vertical}}label{{display:block;margin-top:9px}}details{{margin-top:10px}}summary{{cursor:pointer;font-weight:bold}}#msg{{position:fixed;bottom:18px;left:18px;background:#20242a;color:#fff;padding:11px 15px;border-radius:10px;display:none;z-index:5}}.notice{{background:#f8fafc;padding:12px;border-radius:8px;border-right:4px solid #20242a}}.online{{font-weight:bold}}.empty{{padding:20px;text-align:center;color:#68717c}}@media(max-width:900px){{.grid{{grid-template-columns:repeat(2,1fr)}}.items{{grid-template-columns:1fr}}}}@media(max-width:520px){{.grid{{grid-template-columns:1fr}}}}</style></head>
<body><div class="wrap"><header><h1>مركز متابعة سوق خدمات خيرت</h1><p class="muted">لوحة تشغيل Marketplace متصلة بالـBackend. لا تحتاج لإدخال رابط يدويًا.</p>
<div class="toolbar"><button class="primary" onclick="connectBackend()">اختبار الـBackend وتحديث البيانات</button><button onclick="syncMostaql()">سحب فرص جديدة من مستقل</button><button onclick="location.reload()">تحديث اللوحة</button></div>
<div id="backend" class="notice">جاري اختبار الـBackend...</div></header>
<div id="stats" class="grid"></div><section><input id="search" placeholder="بحث في الفرص والخدمات..." oninput="draw()"></section><section><h2>فرص مستقل</h2><div id="opportunities" class="items"></div></section><section><h2>خدمات خمسات</h2><div id="services" class="items"></div></section><section><h2>Portfolio</h2><div id="portfolio" class="items"></div></section><section><h2>سجل النشاط</h2><ul id="activity"></ul></section></div><div id="msg"></div>
<script>
const ORIGINAL=__SNAPSHOT__;
const API={DEFAULT_BACKEND!r};
let state=structuredClone(ORIGINAL);
function esc(v){{return String(v??'').replace(/[&<>\\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
function status(x){{return String(x.lifecycle||x.status||'DRAFT').toUpperCase()}}
function find(id){{return [...(state.opportunities||[]),...(state.services||[])].find(x=>String(x.id)===String(id))}}
function card(x,isOpp){{const id=esc(x.id),s=status(x),title=esc(x.title),desc=esc(x.description||x.summary||''),offer=esc(x.offer||''),score=Number(x.acquisition_score??x.match_score??0);let b='';if(['DRAFT','OFFER_READY','REJECTED','FAILED'].includes(s))b+=`<button onclick="transition('${{id}}','READY_FOR_REVIEW')">إرسال للمراجعة</button>`;if(s==='READY_FOR_REVIEW')b+=`<button onclick="transition('${{id}}','APPROVED')">اعتماد</button><button class="danger" onclick="transition('${{id}}','REJECTED')">رفض</button>`;if(isOpp&&s==='APPROVED')b+=`<button onclick="transition('${{id}}','SUBMITTED')">تسجيل كمُرسل</button>`;if(isOpp&&s==='SUBMITTED')b+=`<button onclick="transition('${{id}}','WON')">تسجيل فوز</button><button onclick="transition('${{id}}','LOST')">تسجيل خسارة</button>`;if(isOpp&&!['WON','LOST','EXPIRED','CANCELLED'].includes(s))b+=`<button onclick="remoteOffer('${{id}}')">دراسة بـGemini</button>`;if(isOpp&&x.source_url)b+=`<a class="open" target="_blank" rel="noopener" href="${{esc(x.source_url)}}">فتح المشروع على مستقل</a>`;return `<article class="card"><div class="row"><strong>${{title}}</strong><span class="badge">${{esc(s)}}</span></div><p>${{desc}}</p>${{isOpp?`<span class="score">${{score}}% أولوية</span><details open><summary>العرض</summary><textarea id="offer-${{id}}">${{offer}}</textarea><div class="actions"><button onclick="copyOffer('${{id}}')">نسخ العرض</button><button onclick="saveOffer('${{id}}')">حفظ العرض</button><button onclick="remoteOffer('${{id}}')">دراسة بـGemini</button></div></details>`:''}}<div class="actions">${{b}}</div></article>`}}
function draw(){{const opp=state.opportunities||[],services=state.services||[];document.getElementById('stats').innerHTML=`<div class="stat">الخدمات<b>${{services.length}}</b></div><div class="stat">فرص مستقل<b>${{opp.length}}</b></div><div class="stat">للمراجعة<b>${{opp.filter(x=>['READY_FOR_REVIEW','OFFER_READY'].includes(status(x))).length}}</b></div><div class="stat">معتمدة/مرسلة<b>${{opp.filter(x=>['APPROVED','SUBMITTED','WON'].includes(status(x))).length}}</b></div>`;const q=(document.getElementById('search')?.value||'').toLowerCase().trim();const f=a=>a.filter(x=>(x.title+' '+(x.description||'')+' '+status(x)).toLowerCase().includes(q));document.getElementById('opportunities').innerHTML=f(opp).map(x=>card(x,true)).join('')||'<div class="empty">لا توجد فرص.</div>';document.getElementById('services').innerHTML=f(services).map(x=>card(x,false)).join('')||'<div class="empty">لا توجد خدمات.</div>';document.getElementById('portfolio').innerHTML=(state.portfolio||[]).map(x=>`<article class="card"><strong>${{esc(x.title)}}</strong><p>${{esc(x.summary)}}</p></article>`).join('')||'<div class="empty">لا توجد أعمال.</div>';document.getElementById('activity').innerHTML=(state.activity||[]).slice(0,30).map(x=>`<li>${{esc(x.time)}} — ${{esc(x.message)}}</li>`).join('')||'<li>لا يوجد نشاط.</li>'}}
async function req(path,payload){{const r=await fetch(API+path,{{method:payload?'POST':'GET',headers:{{'Content-Type':'application/json'}},body:payload?JSON.stringify(payload):undefined}});const d=await r.json();if(!r.ok||d.ok===false)throw new Error(d.error||d.message||'Backend error');return d}}
async function connectBackend(){{try{{const d=await req('/api/health');document.getElementById('backend').innerHTML=`<span class="online">Backend متصل.</span> ${{esc(d.persistence||'')}} — Gemini: ${{d.gemini_offers?'مفعل':'غير مفعل'}} — Mostaql: ${{d.live_mostaql?'متاح':'غير متاح'}}`;await loadRemote()}}catch(e){{document.getElementById('backend').textContent='Backend غير متاح: '+e.message;toast(e.message)}}}}
async function loadRemote(){{try{{state=await req('/api/state');draw();toast('تم تحديث البيانات من Backend')}}catch(e){{toast('تعذر تحديث Backend: '+e.message)}}}}
async function syncMostaql(){{try{{const d=await req('/api/mostaql/sync',{{limit:12}});toast(d.message);await loadRemote()}}catch(e){{toast(e.message)}}}}
async function remoteOffer(id){{try{{const d=await req('/api/mostaql/offer',{{id}});const x=find(id);if(x){{x.offer=d.offer;x.status=x.lifecycle='OFFER_READY';draw();toast('تمت دراسة المشروع بواسطة Gemini')}}}}catch(e){{toast(e.message)}}}}
async function transition(id,to){{try{{const d=await req('/api/marketplace/opportunity-status',{{id,status:to}});const x=find(id);if(x)Object.assign(x,d.opportunity);draw();toast('تم حفظ الحالة على Backend')}}catch(e){{toast(e.message)}}}}
async function saveOffer(id){{const x=find(id),el=document.getElementById('offer-'+id);if(!x||!el)return; x.offer=el.value.trim();try{{await req('/api/action',{{action:'update_offer',id,offer:x.offer}});draw();toast('تم حفظ العرض')}}catch(e){{toast(e.message)}}}}
async function copyOffer(id){{const x=find(id);if(!x)return;try{{await navigator.clipboard.writeText(x.offer||'');toast('تم نسخ العرض')}}catch(e){{toast('تعذر النسخ من المتصفح')}}}}
function toast(t){{const e=document.getElementById('msg');e.textContent=t;e.style.display='block';clearTimeout(window.__toast);window.__toast=setTimeout(()=>e.style.display='none',2500)}}
draw();connectBackend();
</script></body></html>'''
    return html.replace("__SNAPSHOT__", snapshot)


def main() -> None:
    DASHBOARD_FILE.write_text(render(load_state()), encoding="utf-8")
    print(DASHBOARD_FILE)


if __name__ == "__main__":
    main()
