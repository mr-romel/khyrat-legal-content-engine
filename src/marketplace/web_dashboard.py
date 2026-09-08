"""Vercel dashboard for live Marketplace sourcing and AI-assisted preparation."""
from __future__ import annotations

import html
import json
from typing import Any


def _e(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def render(state: dict[str, Any]) -> str:
    services = state.get("services", [])
    opportunities = state.get("opportunities", [])
    activity = state.get("activity", [])[:15]
    service_cards = []
    for service in services:
        sid = _e(service.get("id"))
        image = service.get("image_data_url", "")
        image_html = f'<img class="cover" src="{_e(image)}" alt="صورة { _e(service.get("title")) }">' if image else '<div class="cover empty">لم يتم توليد الصورة بعد</div>'
        service_cards.append(f'''<article class="card">
{image_html}<h3>{_e(service.get("title"))}</h3><p>{_e(service.get("description"))}</p>
<ul>{''.join(f'<li>{_e(x)}</li>' for x in service.get('deliverables', []))}</ul>
<div class="chips">{''.join(f'<span>{_e(x)}</span>' for x in service.get('keywords', [])[:6])}</div>
<div class="actions"><button onclick="genImage('{sid}')">{ 'تحديث الصورة' if image else 'توليد صورة جاهزة' }</button></div>
</article>''')

    opp_cards = []
    for opp in opportunities:
        oid = _e(opp.get("id"))
        offer = opp.get("offer", "")
        url = _e(opp.get("source_url", ""))
        score = int(opp.get("match_score", opp.get("acquisition_score", 0)) or 0)
        opp_cards.append(f'''<article class="card opp"><div class="row"><h3>{_e(opp.get('title'))}</h3><strong>{score}% مطابقة</strong></div>
<p>{_e(opp.get('description'))}</p><p><b>لماذا؟</b></p><ul>{''.join(f'<li>{_e(x)}</li>' for x in opp.get('rationale', opp.get('ranking_reasons', []))[:6])}</ul>
<p><a class="open" href="{url}" target="_blank" rel="noopener">فتح المشروع على مستقل</a></p>
<label>العرض المقترح بعد تحليل Gemini<textarea id="offer-{oid}">{_e(offer)}</textarea></label>
<div class="actions"><button onclick="genOffer('{oid}')">{ 'إعادة دراسة العرض بـ Gemini' if offer else 'دراسة المشروع بـ Gemini وكتابة العرض' }</button><button onclick="copyText('offer-{oid}')">نسخ العرض</button></div>
<p class="muted">المشروع لا يتم إرساله تلقائيًا إلى مستقل؛ الاعتماد والإرسال يظلان يدويين.</p></article>''')

    activity_html = ''.join(f'<li>{_e(x.get("time"))} — {_e(x.get("message"))}</li>' for x in activity) or '<li>لا يوجد نشاط.</li>'
    return f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-store"><title>خيرت — Marketplace Command Center</title><style>
body{{margin:0;background:#f4f6f8;color:#20242a;font-family:Tahoma,Arial,sans-serif}}.wrap{{max-width:1250px;margin:auto;padding:18px}}header,.panel,.card{{background:#fff;border:1px solid #dfe3e8;border-radius:16px;padding:18px}}header{{margin-bottom:14px}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}}.row{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}}.muted{{color:#68717c;font-size:13px}}button,.open{{border:1px solid #cbd1d8;border-radius:9px;padding:9px 13px;background:#f7f8fa;cursor:pointer;text-decoration:none;color:#20242a}}button.primary,.open{{background:#20242a;color:#fff}}.actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}textarea{{width:100%;min-height:210px;box-sizing:border-box;border:1px solid #cbd1d8;border-radius:10px;padding:12px;line-height:1.8;font:inherit}}.cover{{width:100%;aspect-ratio:1700/970;object-fit:cover;border-radius:12px;background:#eef1f4;display:block}}.empty{{display:flex;align-items:center;justify-content:center;color:#6b7280}}.chips{{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}}.chips span{{background:#eef2f6;border-radius:999px;padding:5px 9px;font-size:12px}}section{{margin-top:14px}}h1,h2,h3{{margin-top:0}}.toolbar{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}}#msg{{position:fixed;bottom:18px;left:18px;background:#20242a;color:#fff;padding:10px 14px;border-radius:10px;display:none}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap"><header><h1>مركز فرص وخدمات خيرت</h1><p>مستقل: سحب فرص قانونية حاليًا → فلترة حسب المحاماة والعقود والقانون المصري → تحليل حالة كل مشروع → عرض مهني بواسطة Gemini.</p><div class="toolbar"><button class="primary" onclick="syncMostaql()">سحب فرص جديدة من مستقل الآن</button><button onclick="location.reload()">تحديث</button></div></header>
<section class="panel"><h2>فرص مستقل — قانون وعقود وشركات</h2><p class="muted">يتم الاحتفاظ بالفرص ذات الصلة القانونية فقط. لا يوجد تسجيل دخول أو إرسال تلقائي للعروض.</p><div class="grid">{''.join(opp_cards) or '<article class="card">اضغط سحب فرص جديدة من مستقل.</article>'}</div></section>
<section class="panel"><h2>خدمات خمسات المقترحة</h2><p class="muted">الخدمات مبنية على تخصصك: عقود، شركات، عمل، تجاري واستشارات. كل خدمة لها مخرجات وكلمات مفتاحية وصورة غلاف قابلة للتوليد بمقاس 1700×970.</p><div class="grid">{''.join(service_cards) or '<article class="card">لا توجد خدمات.</article>'}</div></section>
<section class="panel"><h2>النشاط</h2><ul>{activity_html}</ul></section></div><div id="msg"></div><script>
const msg=t=>{{const e=document.getElementById('msg');e.textContent=t;e.style.display='block';setTimeout(()=>e.style.display='none',3500)}};
async function post(path,payload){{const r=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload||{{}})}});const d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||d.message||'حدث خطأ');return d}}
async function syncMostaql(){{msg('جاري سحب وتحليل فرص مستقل...');try{{const d=await post('/api/mostaql/sync',{{limit:12}});msg(d.message);setTimeout(()=>location.reload(),700)}}catch(e){{msg(e.message)}}}}
async function genOffer(id){{msg('Gemini يدرس المشروع ويكتب عرضًا مخصصًا...');try{{const d=await post('/api/mostaql/offer',{{id}});document.getElementById('offer-'+id).value=d.offer;msg('تم توليد العرض المهني للمشروع')}}catch(e){{msg(e.message)}}}}
async function genImage(id){{msg('Gemini يولد صورة الخدمة...');try{{const d=await post('/api/khamsat/image',{{id}});location.reload();msg('تم توليد صورة الخدمة')}}catch(e){{msg(e.message)}}}}
async function copyText(id){{const t=document.getElementById(id);await navigator.clipboard.writeText(t.value);msg('تم نسخ العرض')}}
</script></body></html>'''
