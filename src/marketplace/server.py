"""Private Marketplace control center.

The server binds to localhost only. Remote access is provided separately by
Cloudflare Tunnel + Cloudflare Access, never by opening port 8765 directly.
Marketplace does not import Core modules.
"""
from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from marketplace_mvp import DATA_FILE, _now, build_offer, load_state, save_state, seed_demo
from marketplace.pipeline import ensure_initial_assets, ingest_mostaql_opportunity, offer_quality, summarize_pipeline
from marketplace.review import approve, mark_ready, reject, metrics

HOST = "127.0.0.1"
PORT = 8765


def esc(value: object) -> str:
    return html.escape(str(value))


def action_buttons(item: dict) -> str:
    item_id = esc(item.get("id", ""))
    status = item.get("status", "DRAFT")
    out: list[str] = []
    if status in {"DRAFT", "OFFER_READY", "REJECTED", "FAILED"}:
        out.append(f'<button onclick="act(\'{item_id}\',\'ready\')">إرسال للمراجعة</button>')
    if status == "READY_FOR_REVIEW":
        out.append(f'<button onclick="act(\'{item_id}\',\'approve\')">اعتماد</button>')
        out.append(f'<button onclick="act(\'{item_id}\',\'reject\')">رفض</button>')
    if item_id.startswith("opp-"):
        out.append(f'<button onclick="act(\'{item_id}\',\'regenerate_offer\')">إعادة توليد العرض</button>')
    return "".join(out)


def render_dashboard(state: dict) -> str:
    m = metrics(state)
    p = summarize_pipeline(state)
    services = state.get("services", [])
    opportunities = state.get("opportunities", [])
    portfolio = state.get("portfolio", [])
    activity = state.get("activity", [])[:20]

    service_cards = "".join(
        f'<article><div class="row"><b>{esc(x.get("title"))}</b><span>{esc(x.get("status"))}</span></div>'
        f'<p>{esc(x.get("description"))}</p><div class="muted">المخرجات</div><ul>{"".join(f"<li>{esc(v)}</li>" for v in x.get("deliverables", []))}</ul>'
        f'<div class="actions">{action_buttons(x)}</div></article>'
        for x in services
    ) or '<article>لا توجد خدمات.</article>'

    portfolio_cards = "".join(
        f'<article><div class="row"><b>{esc(x.get("title"))}</b><span>{esc(x.get("status"))}</span></div>'
        f'<p>{esc(x.get("summary"))}</p><div class="tags">{" ".join(f"<span>{esc(v)}</span>" for v in x.get("skills", []))}</div></article>'
        for x in portfolio
    ) or '<article>لا توجد أعمال.</article>'

    opportunity_cards = "".join(
        f'<article><div class="row"><b>{esc(x.get("title"))}</b><span class="score">{int(x.get("match_score", 0))}% Match</span></div>'
        f'<p>{esc(x.get("description"))}</p><p><b>السعر:</b> {int(x.get("suggested_price_egp", 0))} جنيه · <b>المدة:</b> {int(x.get("suggested_days", 0))} أيام</p>'
        f'<ul>{"".join(f"<li>{esc(v)}</li>" for v in x.get("rationale", []))}</ul>'
        f'<details><summary>العرض الجاهز + Quality Check</summary><pre>{esc(x.get("offer", ""))}</pre><p>Quality: {"PASS" if offer_quality(x)["passed"] else "REVIEW REQUIRED"}</p></details>'
        f'<div class="actions">{action_buttons(x)}</div></article>'
        for x in opportunities
    ) or '<article>لا توجد فرص.</article>'

    activity_html = "".join(f'<li>{esc(x.get("time"))} — {esc(x.get("message"))}</li>' for x in activity) or '<li>لا يوجد نشاط.</li>'

    return f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-store"><title>Khyrat Marketplace Control Center</title><style>
body{{font-family:Arial,Tahoma,sans-serif;background:#f3f5f7;color:#20242a;margin:0}}.wrap{{max-width:1250px;margin:auto;padding:20px}}header,section,article,.stat{{background:#fff;border:1px solid #ddd;border-radius:14px;padding:16px}}header{{margin-bottom:14px}}section{{margin-top:14px}}.grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}}.stat b{{font-size:25px;display:block;margin-top:5px}}.items{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}.row{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}}.muted{{color:#66717d}}.tags{{display:flex;gap:6px;flex-wrap:wrap}}.tags span,.score,.row>span{{background:#eef2f6;border-radius:999px;padding:5px 9px;font-size:12px}}.score{{font-weight:700}}button{{border:1px solid #c9ced5;background:#f7f8fa;border-radius:8px;padding:8px 12px;cursor:pointer}}.actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}}pre{{white-space:pre-wrap;background:#f5f6f8;padding:12px;border-radius:8px;line-height:1.7}}input,textarea{{width:100%;box-sizing:border-box;padding:10px;border:1px solid #c9ced5;border-radius:8px;margin-top:5px}}textarea{{min-height:110px}}form{{display:grid;gap:10px}}.primary{{background:#20242a;color:#fff}}#msg{{position:fixed;bottom:18px;left:18px;background:#20242a;color:#fff;padding:10px 14px;border-radius:10px;display:none}}@media(max-width:900px){{.grid{{grid-template-columns:repeat(2,1fr)}}.items{{grid-template-columns:1fr}}}}@media(max-width:500px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap"><header><h1>Khyrat Marketplace Control Center</h1><p class="muted">Generate → Quality Check → Dashboard Review → Approval → Platform</p><button onclick="location.reload()">تحديث</button></header>
<div class="grid"><div class="stat">الخدمات<b>{m['services']}</b></div><div class="stat">Portfolio<b>{m['portfolio']}</b></div><div class="stat">فرص مستقل<b>{m['opportunities']}</b></div><div class="stat">Review Queue<b>{m['review_queue']}</b></div><div class="stat">Ready Offers<b>{p['ready_offers']}</b></div><div class="stat">Avg Match<b>{p['avg_match_score']}%</b></div></div>
<section><h2>إضافة فرصة من مستقل</h2><p class="muted">الصق عنوان ووصف المشروع هنا. لا يوجد تسجيل دخول أو إرسال تلقائي للمنصة.</p><form onsubmit="return addOpportunity(event)"><label>العنوان<input id="oppTitle" required></label><label>الوصف<textarea id="oppDescription" required></textarea></label><button class="primary" type="submit">تحليل الفرصة وتوليد العرض</button></form></section>
<section><h2>خدمات خمسات</h2><div class="items">{service_cards}</div></section>
<section><h2>Portfolio</h2><div class="items">{portfolio_cards}</div></section>
<section><h2>فرص مستقل والعروض</h2><div class="items">{opportunity_cards}</div></section>
<section><h2>Activity Log</h2><ul>{activity_html}</ul></section>
<section><h2>الوضع الأمني</h2><p>الخادم يستمع على 127.0.0.1 فقط. للوصول من خارج المنزل استخدم Cloudflare Tunnel + Cloudflare Access. لا تستخدم Port Forwarding ولا Tunnel عام بدون Access.</p></section>
</div><div id="msg"></div><script>
async function act(id, action){{const r=await fetch('/api/action',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id,action}})}});const d=await r.json();show(d.message||d.error||'تم');setTimeout(()=>location.reload(),500);}}
async function addOpportunity(e){{e.preventDefault();const r=await fetch('/api/opportunity',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{title:document.getElementById('oppTitle').value,description:document.getElementById('oppDescription').value}})}});const d=await r.json();show(d.message||d.error||'تم');if(d.ok)setTimeout(()=>location.reload(),500);return false;}}
function show(t){{const m=document.getElementById('msg');m.textContent=t;m.style.display='block';setTimeout(()=>m.style.display='none',3000);}}
</script></body></html>'''


def handle_action(payload: dict) -> tuple[bool, str]:
    state = load_state()
    item_id = payload.get("id", "")
    action = payload.get("action", "")
    item = next((x for group in (state.get("services", []), state.get("opportunities", [])) for x in group if x.get("id") == item_id), None)
    if not item:
        return False, "العنصر غير موجود"
    try:
        if action == "ready":
            result = mark_ready(item)
        elif action == "approve":
            result = approve(item)
        elif action == "reject":
            result = reject(item)
        elif action == "regenerate_offer" and item_id.startswith("opp-"):
            item["offer"] = build_offer(item)
            item["status"] = "OFFER_READY"
            result = None
        else:
            return False, "الإجراء غير مسموح لهذه الحالة"
    except ValueError as exc:
        return False, str(exc)
    state.setdefault("activity", []).insert(0, {"time": result.reviewed_at if result else _now(), "message": f"{action}: {item_id}"})
    save_state(state)
    return True, "تم تنفيذ الإجراء"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: str, content_type: str = "text/html; charset=utf-8"):
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, render_dashboard(load_state()))
        elif path == "/api/state":
            self._send(200, json.dumps(load_state(), ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/api/health":
            self._send(200, json.dumps({"ok": True, "data_file": str(DATA_FILE), "binding": HOST}, ensure_ascii=False), "application/json; charset=utf-8")
        else:
            self._send(404, "Not Found")

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self._json_body()
            if path == "/api/action":
                ok, message = handle_action(payload)
                self._send(200 if ok else 400, json.dumps({"ok": ok, "message": message, "error": None if ok else message}, ensure_ascii=False), "application/json; charset=utf-8")
                return
            if path == "/api/opportunity":
                title = str(payload.get("title", "")).strip()
                description = str(payload.get("description", "")).strip()
                if not title or not description:
                    raise ValueError("العنوان والوصف مطلوبان")
                state = load_state()
                item = ingest_mostaql_opportunity(state, title, description)
                save_state(state)
                self._send(200, json.dumps({"ok": True, "message": f"تم تحليل الفرصة — Match {item.get('match_score', 0)}%", "opportunity": item}, ensure_ascii=False), "application/json; charset=utf-8")
                return
            self._send(404, json.dumps({"error": "Not Found"}), "application/json; charset=utf-8")
        except Exception as exc:
            self._send(400, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), "application/json; charset=utf-8")

    def log_message(self, format, *args):
        print(f"[marketplace] {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--seed-demo", action="store_true")
    args = parser.parse_args()
    state = load_state()
    if args.seed_demo:
        seed_demo(state)
        ensure_initial_assets(state)
        save_state(state)
    server = ThreadingHTTPServer((HOST, args.port), Handler)
    print(f"Khyrat Marketplace Control Center: http://{HOST}:{args.port}")
    print("Private: listening on localhost only. Remote access must use Cloudflare Tunnel + Access.")
    server.serve_forever()


if __name__ == "__main__":
    main()
