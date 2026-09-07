"""Private Marketplace control center.

Local-only dashboard. Marketplace is isolated from Core and never logs in to,
submits to, or manages a platform account automatically.
"""
from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from marketplace_mvp import DATA_FILE, _now, build_offer, load_state, save_state, seed_demo
from marketplace.pipeline import ensure_initial_assets, ingest_mostaql_opportunity, offer_quality
from marketplace.opportunity_queue import queue_metrics, rank_queue, transition as opp_transition
from marketplace.review import approve, mark_ready, reject, metrics
from marketplace.revenue import analytics, record_outcome
from marketplace.followup import due_followups, prepare_followup

HOST = "127.0.0.1"
PORT = 8765
STATUSES = {"DRAFT", "OFFER_READY", "READY_FOR_REVIEW", "APPROVED", "READY_TO_PUBLISH", "PUBLISHED", "SUBMITTED", "WON", "LOST", "EXPIRED", "CANCELLED", "REJECTED", "FAILED", "PAUSED"}
TERMINAL = {"WON", "LOST", "EXPIRED", "CANCELLED"}


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def safe_link(value: object) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return html.escape(raw, quote=True)


def status_of(item: dict) -> str:
    return str(item.get("lifecycle", item.get("status", "DRAFT"))).upper()


def log_activity(state: dict, message: str) -> None:
    state.setdefault("activity", []).insert(0, {"time": _now(), "message": message})
    state["activity"] = state["activity"][:100]


def action_buttons(item: dict) -> str:
    iid = esc(item.get("id")); status = status_of(item)
    out: list[str] = []
    if status in {"DRAFT", "OFFER_READY", "REJECTED", "FAILED"}:
        out.append(f'<button onclick="act(\'{iid}\',\'ready\')">إرسال للمراجعة</button>')
    if status == "READY_FOR_REVIEW":
        out.append(f'<button onclick="act(\'{iid}\',\'approve\')">اعتماد</button>')
        out.append(f'<button onclick="act(\'{iid}\',\'reject\')">رفض</button>')
    if iid.startswith("opp-"):
        if status == "APPROVED":
            out.append(f'<button onclick="act(\'{iid}\',\'submit\')">تسجيل كمُرسل</button>')
        if status == "SUBMITTED":
            out.append(f'<button onclick="winOpportunity(\'{iid}\')">تسجيل فوز</button>')
            out.append(f'<button onclick="act(\'{iid}\',\'lost\')">تسجيل خسارة</button>')
            out.append(f'<button onclick="act(\'{iid}\',\'follow_up\')">تمت المتابعة</button>')
        if status not in TERMINAL:
            out.append(f'<button onclick="act(\'{iid}\',\'regenerate_offer\')">إعادة توليد العرض</button>')
    return "".join(out)


def status_select(item: dict) -> str:
    iid = esc(item.get("id")); current = status_of(item)
    opts = "".join(f'<option value="{s}" {"selected" if s == current else ""}>{s}</option>' for s in sorted(STATUSES))
    return f'<select id="status-{iid}">{opts}</select><button onclick="setStatus(\'{iid}\')">تغيير الحالة يدويًا</button>'


def render_dashboard(state: dict) -> str:
    m = metrics(state)
    q = queue_metrics(state)
    revenue = analytics(state)
    services = state.get("services", [])
    portfolio = state.get("portfolio", [])
    opportunities = rank_queue(state)
    due = due_followups(state, _now())
    activity = state.get("activity", [])[:30]

    service_cards = []
    for item in services:
        iid = esc(item.get("id"))
        service_cards.append(
            f'<article class="item searchable" data-search="{esc(item.get("title"))} {esc(item.get("description"))} {esc(status_of(item))}">'
            f'<div class="row"><b>{esc(item.get("title"))}</b><span>{esc(status_of(item))}</span></div>'
            f'<p>{esc(item.get("description"))}</p><ul>{"".join(f"<li>{esc(v)}</li>" for v in item.get("deliverables", []))}</ul>'
            f'<details><summary>تعديل الخدمة</summary><label>العنوان<input id="title-{iid}" value="{esc(item.get("title"))}"></label>'
            f'<label>الوصف<textarea id="desc-{iid}">{esc(item.get("description"))}</textarea></label>'
            f'<button onclick="saveItem(\'{iid}\',\'service\')">حفظ التعديل</button></details>'
            f'<div class="actions">{action_buttons(item)}</div><div class="manual">{status_select(item)}</div></article>'
        )

    opportunity_cards = []
    for item in opportunities:
        iid = esc(item.get("id")); offer_id = f"offer-{iid}"; status = status_of(item)
        url = safe_link(item.get("source_url"))
        link = f'<a class="open-link" href="{url}" target="_blank" rel="noopener noreferrer">فتح المشروع على مستقل</a>' if url else '<span class="muted">لا يوجد رابط محفوظ</span>'
        reasons = item.get("ranking_reasons", item.get("rationale", []))[:5]
        next_action = item.get("next_action") or ("راجع العرض ثم اعتمده" if status in {"OFFER_READY", "READY_FOR_REVIEW"} else "افتح المشروع ونفذ الخطوة التالية")
        price = int(item.get("suggested_price_usd", 5)); days = int(item.get("suggested_days", 3))
        quality = offer_quality(item)
        opportunity_cards.append(
            f'<article class="item searchable" data-search="{esc(item.get("title"))} {esc(item.get("description"))} {esc(status)} {price}">'
            f'<div class="row"><b>{esc(item.get("title"))}</b><span>{int(item.get("acquisition_score", item.get("match_score", 0)))}% أولوية</span></div>'
            f'<p>{esc(item.get("description"))}</p><p><b>السعر:</b> ${price} · <b>المدة:</b> {days} أيام · <b>الحالة:</b> {esc(status)}</p>'
            f'<p><b>ماذا أفعل الآن؟</b> {esc(next_action)}</p><p>{link}</p>'
            f'<b>لماذا رشحها النظام؟</b><ul>{"".join(f"<li>{esc(v)}</li>" for v in reasons) or "<li>لا توجد أسباب مسجلة.</li>"}</ul>'
            f'<details open><summary>العرض — مراجعة وتعديل ونسخ</summary><textarea id="{offer_id}">{esc(item.get("offer"))}</textarea>'
            f'<div class="actions"><button onclick="copyOffer(\'{offer_id}\')">نسخ العرض</button>'
            f'<button onclick="saveOffer(\'{iid}\')">حفظ تعديل العرض</button><button onclick="regenerateOffer(\'{iid}\')">إعادة توليد العرض</button></div>'
            f'<p>فحص الجودة: <b>{"ناجح" if quality.get("passed") else "يحتاج مراجعة"}</b></p></details>'
            f'<details><summary>تعديل الفرصة والسعر والمدة والملاحظات</summary>'
            f'<label>العنوان<input id="title-{iid}" value="{esc(item.get("title"))}"></label>'
            f'<label>الوصف<textarea id="desc-{iid}">{esc(item.get("description"))}</textarea></label>'
            f'<label>السعر بالدولار (5 ومضاعفاتها)<input id="price-{iid}" type="number" min="5" step="5" value="{price}"></label>'
            f'<label>المدة بالأيام<input id="days-{iid}" type="number" min="1" value="{days}"></label>'
            f'<label>ملاحظاتك<textarea id="notes-{iid}">{esc(item.get("notes"))}</textarea></label>'
            f'<button onclick="saveItem(\'{iid}\',\'opportunity\')">حفظ التعديل</button></details>'
            f'<div class="actions">{action_buttons(item)}</div><div class="manual">{status_select(item)}</div></article>'
        )

    due_cards = []
    for item in due:
        url = safe_link(item.get("source_url"))
        link = f'<a class="open-link" href="{url}" target="_blank">فتح المشروع</a>' if url else "لا يوجد رابط"
        due_cards.append(f'<article><div class="row"><b>{esc(item.get("title"))}</b><span>{esc(status_of(item))}</span></div><p>موعد المتابعة: {esc(item.get("next_followup_at"))}</p><p>{link}</p></article>')

    portfolio_cards = [f'<article><b>{esc(x.get("title"))}</b><p>{esc(x.get("summary"))}</p></article>' for x in portfolio]
    activity_html = "".join(f'<li>{esc(x.get("time"))} — {esc(x.get("message"))}</li>' for x in activity) or '<li>لا يوجد نشاط.</li>'
    service_html = "".join(service_cards) or "<article>لا توجد خدمات.</article>"
    opportunity_html = "".join(opportunity_cards) or "<article>لا توجد فرص.</article>"
    due_html = "".join(due_cards) or "<article>لا توجد متابعة مستحقة الآن.</article>"
    portfolio_html = "".join(portfolio_cards) or "<article>لا توجد أعمال.</article>"

    return f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-store"><title>مركز متابعة سوق خدمات خيرت</title><style>
body{{font-family:Arial,Tahoma,sans-serif;background:#f3f5f7;color:#20242a;margin:0}}.wrap{{max-width:1250px;margin:auto;padding:20px}}header,section,article,.stat{{background:#fff;border:1px solid #ddd;border-radius:14px;padding:16px}}section{{margin-top:14px}}.grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}}.items{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}.row{{display:flex;justify-content:space-between;gap:12px}}.muted{{color:#66717d}}.score,.row>span{{background:#eef2f6;border-radius:999px;padding:5px 9px;font-size:12px}}button{{border:1px solid #c9ced5;background:#f7f8fa;border-radius:8px;padding:8px 12px;cursor:pointer}}.actions,.manual{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}}.open-link{{display:inline-block;background:#20242a;color:#fff;text-decoration:none;border-radius:8px;padding:8px 12px}}textarea{{white-space:pre-wrap;background:#f5f6f8;padding:12px;border-radius:8px;line-height:1.7;box-sizing:border-box;width:100%;min-height:120px}}input,select{{width:100%;box-sizing:border-box;padding:10px;border:1px solid #c9ced5;border-radius:8px;margin-top:5px}}form{{display:grid;gap:10px}}.stat b{{font-size:25px;display:block;margin-top:5px}}.primary{{background:#20242a;color:#fff}}#msg{{position:fixed;bottom:18px;left:18px;background:#20242a;color:#fff;padding:10px 14px;border-radius:10px;display:none}}@media(max-width:900px){{.grid{{grid-template-columns:repeat(2,1fr)}}.items{{grid-template-columns:1fr}}}}@media(max-width:500px){{.grid{{grid-template-columns:1fr}}}}</style></head><body><div class="wrap">
<header><h1>مركز متابعة سوق خدمات خيرت</h1><p class="muted">إضافة → تحليل → عرض → تعديل → مراجعة → اعتماد → تنفيذ يدوي على المنصة</p><input id="search" placeholder="بحث في الفرص والخدمات والحالة والسعر..." oninput="filterCards()"><button onclick="location.reload()">تحديث</button></header>
<div class="grid"><div class="stat">الخدمات<b>{m['services']}</b></div><div class="stat">نماذج الأعمال<b>{m['portfolio']}</b></div><div class="stat">فرص مستقل<b>{q['total']}</b></div><div class="stat">أولوية عالية<b>{q['high']}</b></div><div class="stat">في انتظار المراجعة<b>{q['review']}</b></div><div class="stat">متابعات مستحقة<b>{len(due)}</b></div></div>
<section><h2>إضافة فرصة يدويًا</h2><p class="muted">السعر بالدولار ويجب أن يكون 5$ أو أحد مضاعفاته: 5، 10، 15، 20...</p><form onsubmit="return addOpportunity(event)"><label>العنوان<input id="oppTitle" required></label><label>الوصف<textarea id="oppDescription" required></textarea></label><label>رابط المشروع في مستقل<input id="oppUrl" type="url" placeholder="https://mostaql.com/project/..."></label><label>ملاحظاتك<textarea id="oppNotes"></textarea></label><label>السعر المقترح بالدولار<input id="oppPrice" type="number" min="5" step="5" value="5"></label><label>المدة بالأيام<input id="oppDays" type="number" min="1" value="3"></label><button class="primary" type="submit">إضافة وتحليل وتوليد العرض</button></form></section>
<section><h2>مهام اليوم</h2><div class="items">{due_html}</div></section><section><h2>الفرص — لماذا رشحها النظام وماذا أفعل الآن؟</h2><div class="items">{opportunity_html}</div></section><section><h2>خدمات خمسات — تعديل واعتماد</h2><div class="items">{service_html}</div></section><section><h2>نماذج الأعمال</h2><div class="items">{portfolio_html}</div></section>
<section><h2>الإيرادات والهدف</h2><p>المحقق هذا الشهر: <b>{revenue['revenue_egp']:.0f} ج</b> · المتبقي من 20,000: <b>{revenue['remaining_to_target_egp']:.0f} ج</b> · التحويل: <b>{revenue['conversion_pct']:.1f}%</b> · القيمة المتوقعة: <b>{revenue['expected_open_egp']:.0f} ج</b></p></section>
<section><h2>سجل النشاط</h2><ul>{activity_html}</ul></section><section><h2>الوضع الأمني</h2><p>الخادم محلي على 127.0.0.1 فقط. لا يوجد تسجيل دخول أو إرسال تلقائي للمنصات.</p></section></div><div id="msg"></div>
<script>async function post(url,payload){{const r=await fetch(url,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});const d=await r.json();show(d.message||d.error||'تم');if(d.ok)setTimeout(()=>location.reload(),400);return d}}async function act(id,action,extra={{}}){{return post('/api/action',Object.assign({{id,action}},extra))}}async function setStatus(id){{return post('/api/action',{{id,action:'set_status',status:document.getElementById('status-'+id).value}})}}async function saveItem(id,kind){{const p={{id,action:'edit',kind,title:document.getElementById('title-'+id).value,description:document.getElementById('desc-'+id).value}};if(kind==='opportunity'){{p.price_usd=Number(document.getElementById('price-'+id).value);p.days=Number(document.getElementById('days-'+id).value);p.notes=document.getElementById('notes-'+id).value}}return post('/api/action',p)}}async function saveOffer(id){{return post('/api/action',{{id,action:'edit_offer',offer:document.getElementById('offer-'+id).value}})}}async function regenerateOffer(id){{return post('/api/action',{{id,action:'regenerate_offer'}})}}async function winOpportunity(id){{const v=prompt('قيمة الصفقة بالجنيه المصري:');if(v===null)return;const n=Number(v);if(!Number.isFinite(n)||n<0){{show('أدخل قيمة صحيحة');return}}return act(id,'won',{{amount_egp:n}})}}async function copyOffer(id){{const el=document.getElementById(id);try{{await navigator.clipboard.writeText(el.value);show('تم نسخ العرض')}}catch(e){{el.focus();el.select();document.execCommand('copy');show('تم نسخ العرض')}}}}async function addOpportunity(e){{e.preventDefault();await post('/api/opportunity',{{title:oppTitle.value,description:oppDescription.value,source_url:oppUrl.value,notes:oppNotes.value,price_usd:Number(oppPrice.value),days:Number(oppDays.value)}});return false}}function filterCards(){{const q=search.value.trim().toLowerCase();document.querySelectorAll('.searchable').forEach(x=>x.style.display=x.dataset.search.toLowerCase().includes(q)?'block':'none')}}function show(t){{const m=document.getElementById('msg');m.textContent=t;m.style.display='block';setTimeout(()=>m.style.display='none',3000)}}</script></body></html>'''


def find_item(state: dict, item_id: str) -> dict | None:
    return next((item for group in (state.get("services", []), state.get("opportunities", [])) for item in group if item.get("id") == item_id), None)


def handle_action(payload: dict) -> tuple[bool, str]:
    state = load_state()
    iid = str(payload.get("id", "")); action = str(payload.get("action", "")); item = find_item(state, iid)
    if not item:
        return False, "العنصر غير موجود"
    try:
        if action == "edit":
            item["title"] = str(payload.get("title", item.get("title", ""))).strip()
            item["description"] = str(payload.get("description", item.get("description", ""))).strip()
            if not item["title"] or not item["description"]:
                return False, "العنوان والوصف مطلوبان"
            if iid.startswith("opp-"):
                price = int(payload.get("price_usd", item.get("suggested_price_usd", 5))); days = int(payload.get("days", item.get("suggested_days", 3)))
                if price < 5 or price % 5: return False, "سعر مستقل يجب أن يكون 5$ أو مضاعفاته"
                if days < 1: return False, "المدة يجب أن تكون يومًا واحدًا على الأقل"
                item["suggested_price_usd"] = price; item["suggested_price_egp"] = price * 50; item["suggested_days"] = days; item["notes"] = str(payload.get("notes", "")).strip()
            log_activity(state, f"تم تعديل {iid}")
        elif action == "edit_offer":
            item["offer"] = str(payload.get("offer", "")).strip()
            if not item["offer"]: return False, "العرض لا يمكن أن يكون فارغًا"
            item["status"] = item["lifecycle"] = "OFFER_READY"; log_activity(state, f"تم تعديل العرض: {iid}")
        elif action == "set_status":
            target = str(payload.get("status", "")).upper()
            if target not in STATUSES: return False, "حالة غير صالحة"
            item["status"] = item["lifecycle"] = target; item["updated_at"] = _now(); log_activity(state, f"تغيير يدوي للحالة: {iid} → {target}")
        elif iid.startswith("opp-") and action == "submit":
            opp_transition(item, "SUBMITTED", _now()); log_activity(state, f"تسجيل إرسال: {iid}")
        elif iid.startswith("opp-") and action in {"won", "lost"}:
            amount = payload.get("amount_egp"); record_outcome(item, "WON" if action == "won" else "LOST", _now(), float(amount) if amount is not None else None); log_activity(state, f"تسجيل {action}: {iid}")
        elif iid.startswith("opp-") and action == "follow_up":
            if status_of(item) != "SUBMITTED": return False, "المتابعة متاحة فقط للفرص المرسلة"
            now = _now(); prepare_followup(item, now); item["updated_at"] = now; log_activity(state, f"follow_up: {iid}")
        elif action == "ready":
            mark_ready(item); item["lifecycle"] = item["status"]; item["updated_at"] = _now(); log_activity(state, f"إرسال للمراجعة: {iid}")
        elif action == "approve":
            approve(item); item["lifecycle"] = item["status"]; item["updated_at"] = _now(); log_activity(state, f"اعتماد: {iid}")
        elif action == "reject":
            reject(item); item["lifecycle"] = item["status"]; item["updated_at"] = _now(); log_activity(state, f"رفض: {iid}")
        elif action == "regenerate_offer" and iid.startswith("opp-"):
            item["offer"] = build_offer(item); item["status"] = item["lifecycle"] = "OFFER_READY"; item["updated_at"] = _now(); log_activity(state, f"إعادة توليد العرض: {iid}")
        else:
            return False, "الإجراء غير مسموح لهذه الحالة"
    except (ValueError, TypeError) as exc:
        return False, str(exc)
    save_state(state)
    return True, "تم تنفيذ الإجراء"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: str, content_type: str = "text/html; charset=utf-8"):
        raw = body.encode("utf-8"); self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(raw)
    def _json_body(self):
        length = int(self.headers.get("Content-Length", "0")); return json.loads(self.rfile.read(length) or b"{}")
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/": self._send(200, render_dashboard(load_state()))
        elif path == "/api/state": self._send(200, json.dumps(load_state(), ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/api/health": self._send(200, json.dumps({"ok": True, "data_file": str(DATA_FILE), "binding": HOST}, ensure_ascii=False), "application/json; charset=utf-8")
        else: self._send(404, "Not Found")
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self._json_body()
            if path == "/api/action":
                ok, message = handle_action(payload); self._send(200 if ok else 400, json.dumps({"ok": ok, "message": message, "error": None if ok else message}, ensure_ascii=False), "application/json; charset=utf-8"); return
            if path == "/api/opportunity":
                title = str(payload.get("title", "")).strip(); description = str(payload.get("description", "")).strip(); source_url = str(payload.get("source_url", "")).strip()
                if not title or not description: raise ValueError("العنوان والوصف مطلوبان")
                price = int(payload.get("price_usd", 5)); days = int(payload.get("days", 3))
                if price < 5 or price % 5: raise ValueError("سعر مستقل يجب أن يكون 5$ أو مضاعفاته")
                if days < 1: raise ValueError("المدة يجب أن تكون يومًا واحدًا على الأقل")
                state = load_state(); item = ingest_mostaql_opportunity(state, title, description, source_url); item["suggested_price_usd"] = price; item["suggested_price_egp"] = price * 50; item["suggested_days"] = days; item["notes"] = str(payload.get("notes", "")).strip(); item["offer"] = build_offer(item); item["status"] = item["lifecycle"] = "OFFER_READY"; log_activity(state, f"إضافة فرصة يدويًا: {title}"); save_state(state)
                self._send(200, json.dumps({"ok": True, "message": f"تمت إضافة الفرصة — المطابقة {item.get('match_score', 0)}%", "opportunity": item}, ensure_ascii=False), "application/json; charset=utf-8"); return
            self._send(404, json.dumps({"error": "Not Found"}), "application/json; charset=utf-8")
        except Exception as exc:
            self._send(400, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), "application/json; charset=utf-8")
    def log_message(self, format, *args): print(f"[marketplace] {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--port", type=int, default=PORT); parser.add_argument("--seed-demo", action="store_true"); args = parser.parse_args(); state = load_state()
    if args.seed_demo: seed_demo(state); ensure_initial_assets(state); save_state(state)
    server = ThreadingHTTPServer((HOST, args.port), Handler); print(f"مركز متابعة سوق خدمات خيرت: http://{HOST}:{args.port}"); server.serve_forever()


if __name__ == "__main__": main()
