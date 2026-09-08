"""Vercel dashboard for live Marketplace sourcing and AI-assisted preparation."""
from __future__ import annotations

import html
from typing import Any


def _e(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _status_label(status: str) -> str:
    return {"SUBMITTED": "تم التقديم", "IGNORED": "تجاهل", "REJECTED": "مرفوضة", "OFFER_READY": "عرض جاهز", "NEW": "جديدة"}.get(status, status)


def render(state: dict[str, Any]) -> str:
    services = state.get("services", [])
    opportunities = state.get("opportunities", [])
    activity = state.get("activity", [])[:15]
    mostaql = [x for x in opportunities if str(x.get("platform", "mostaql")).lower() == "mostaql"]

    service_cards = []
    for service in services:
        sid = _e(service.get("id"))
        image = service.get("image_data_url", "")
        image_html = f'<img id="image-{sid}" class="cover" src="{_e(image)}" alt="صورة الخدمة">' if image else f'<div id="image-{sid}" class="cover empty">لم يتم توليد الصورة بعد</div>'
        service_cards.append(f'''<article class="card">
{image_html}<h3>{_e(service.get("title"))}</h3><p>{_e(service.get("description"))}</p>
<ul>{''.join(f'<li>{_e(x)}</li>' for x in service.get('deliverables', []))}</ul><div class="chips">{''.join(f'<span>{_e(x)}</span>' for x in service.get('keywords', [])[:6])}</div>
<div class="actions"><button onclick="genImage('{sid}')">توليد/تحديث صورة</button><a id="download-{sid}" class="open" style="display:none" download="khyrat-khamsat-service.jpg">تحميل الصورة</a></div></article>''')

    opp_cards = []
    for opp in mostaql:
        oid = _e(opp.get("id")); offer = opp.get("offer", ""); url = _e(opp.get("source_url", "")); status = str(opp.get("status", opp.get("lifecycle", "NEW"))).upper()
        score = int(opp.get("match_score", opp.get("acquisition_score", 0)) or 0)
        opp_cards.append(f'''<article class="card opp"><div class="row"><h3>{_e(opp.get('title'))}</h3><span class="badge">{_e(_status_label(status))}</span><strong>{score}% مطابقة</strong></div>
<p>{_e(opp.get('description'))}</p><p><b>السعر:</b> ${int(opp.get('suggested_price_usd', 5) or 5)} · <b>المدة:</b> {int(opp.get('suggested_days', 3) or 3)} أيام</p>
<p><a class="open" href="{url}" target="_blank" rel="noopener">فتح المشروع على مستقل</a></p>
<label>العرض المقترح<textarea id="offer-{oid}">{_e(offer)}</textarea></label>
<div class="actions"><button onclick="genOffer('{oid}')">{ 'إعادة توليد العرض' if offer else 'توليد العرض' }</button><button onclick="copyText('offer-{oid}')">نسخ العرض</button><button class="success" onclick="setOppStatus('{oid}','SUBMITTED')">تم التقديم</button><button class="warn" onclick="setOppStatus('{oid}','IGNORED')">تجاهل</button><button class="danger" onclick="setOppStatus('{oid}','REJECTED')">مرفوضة</button></div>
<p class="muted">التقديم الفعلي على مستقل يظل يدويًا؛ زر «تم التقديم» يسجل حالتك فقط ويمنع عودة الفرصة في السحب القادم.</p></article>''')

    activity_html = ''.join(f'<li>{_e(x.get("time"))} — {_e(x.get("message"))}</li>' for x in activity) or '<li>لا يوجد نشاط.</li>'
    return f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-store"><title>خيرت — Marketplace Command Center</title><style>
body{{margin:0;background:#f4f6f8;color:#20242a;font-family:Tahoma,Arial,sans-serif}}.wrap{{max-width:1250px;margin:auto;padding:18px}}header,.panel,.card{{background:#fff;border:1px solid #dfe3e8;border-radius:16px;padding:18px}}header{{margin-bottom:14px}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}}.row{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap}}.muted{{color:#68717c;font-size:13px}}button,.open{{border:1px solid #cbd1d8;border-radius:9px;padding:9px 13px;background:#f7f8fa;cursor:pointer;text-decoration:none;color:#20242a}}.success{{background:#e8f5e9}}.warn{{background:#fff4d6}}.danger{{background:#fde8e8}}.open{{background:#20242a;color:#fff}}.actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}textarea{{width:100%;min-height:210px;box-sizing:border-box;border:1px solid #cbd1d8;border-radius:10px;padding:12px;line-height:1.8;font:inherit}}.cover{{width:100%;aspect-ratio:1700/970;object-fit:cover;border-radius:12px;background:#eef1f4;display:block}}.empty{{display:flex;align-items:center;justify-content:center;color:#6b7280}}.chips{{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}}.chips span,.badge{{background:#eef2f6;border-radius:999px;padding:5px 9px;font-size:12px}}section{{margin-top:14px}}h1,h2,h3{{margin-top:0}}.tabs{{display:flex;gap:8px;margin-top:14px}}.tab{{font-weight:700}}.tab.active{{background:#20242a;color:#fff}}.pane{{display:none;margin-top:14px}}.pane.active{{display:block}}#msg{{position:fixed;bottom:18px;left:18px;background:#20242a;color:#fff;padding:10px 14px;border-radius:10px;display:none}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap"><header><h1>مركز فرص وخدمات خيرت</h1><p>لوحة منفصلة لكل منصة، مع حفظ حالة كل فرصة حتى لا تعود بعد البحث.</p><div class="tabs"><button id="tab-mostaql" class="tab active" onclick="showTab('mostaql')">مستقل</button><button id="tab-khamsat" class="tab" onclick="showTab('khamsat')">خمسات</button></div></header>
<section id="pane-mostaql" class="pane active panel"><h2>فرص مستقل</h2><p class="muted">السحب الجديد يستبعد تلقائيًا الفرص التي سجلتها «تم التقديم» أو «تجاهل» أو «مرفوضة».</p><div class="actions"><button class="open" onclick="syncMostaql()">سحب فرص جديدة من مستقل</button><button onclick="location.reload()">تحديث</button></div><div class="grid">{''.join(opp_cards) or '<article class="card">لا توجد فرص جديدة حاليًا.</article>'}</div></section>
<section id="pane-khamsat" class="pane panel"><h2>خدمات خمسات</h2><p class="muted">الخدمات المقترحة جاهزة للتعديل وتوليد صورة الغلاف بالمقاس المطلوب.</p><div class="grid">{''.join(service_cards) or '<article class="card">لا توجد خدمات.</article>'}</div></section>
<section class="panel"><h2>النشاط</h2><ul>{activity_html}</ul></section></div><div id="msg"></div><script>
const msg=t=>{{const e=document.getElementById('msg');e.textContent=t;e.style.display='block';setTimeout(()=>e.style.display='none',3500)}};
async function post(path,payload){{const r=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload||{{}})}});const d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||d.message||'حدث خطأ');return d}}
function showTab(tab){{for(const x of ['mostaql','khamsat']){{document.getElementById('pane-'+x).classList.toggle('active',x===tab);document.getElementById('tab-'+x).classList.toggle('active',x===tab)}}}}
async function syncMostaql(){{msg('جاري سحب فرص جديدة من مستقل...');try{{const d=await post('/api/mostaql/sync',{{limit:12}});msg(d.message);setTimeout(()=>location.reload(),700)}}catch(e){{msg(e.message)}}}}
async function genOffer(id){{msg('Gemini يدرس المشروع ويكتب عرضًا مخصصًا...');try{{const d=await post('/api/mostaql/offer',{{id}});document.getElementById('offer-'+id).value=d.offer;msg('تم توليد العرض')}}catch(e){{msg(e.message)}}}}
async function setOppStatus(id,status){{const labels={{SUBMITTED:'تم تسجيل التقديم',IGNORED:'تم تجاهل الفرصة',REJECTED:'تم تسجيل الرفض'}};msg('جاري حفظ الحالة...');try{{await post('/api/marketplace/opportunity-status',{{id,status}});msg(labels[status]||'تم الحفظ');setTimeout(()=>location.reload(),500)}}catch(e){{msg(e.message)}}}}
async function genImage(id){{msg('Gemini يولد صورة الخدمة...');try{{const d=await post('/api/khamsat/image',{{id}});const box=document.getElementById('image-'+id);box.outerHTML='<img id="image-'+id+'" class="cover" src="'+d.image_data_url+'" alt="صورة الخدمة">';const link=document.getElementById('download-'+id);link.href=d.image_data_url;link.style.display='inline-block';msg('تم توليد الصورة')}}catch(e){{msg(e.message)}}}}
async function copyText(id){{const t=document.getElementById(id);await navigator.clipboard.writeText(t.value);msg('تم نسخ العرض')}}
</script></body></html>'''
