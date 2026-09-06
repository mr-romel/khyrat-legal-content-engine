"""Private local Marketplace control center.

Binds only to 127.0.0.1. No platform credentials are exposed to the browser.
The Marketplace module remains independent from Core.
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from marketplace_mvp import DATA_FILE, build_offer, load_state, save_state, seed_demo
from marketplace.review import approve, mark_ready, reject, metrics

HOST = "127.0.0.1"
PORT = 8765


def html(state: dict) -> str:
    m = metrics(state)
    def esc(v):
        import html as h
        return h.escape(str(v))
    def buttons(item):
        item_id = esc(item.get("id", ""))
        status = item.get("status", "DRAFT")
        out = []
        if status in {"DRAFT", "OFFER_READY", "REJECTED", "FAILED"}:
            out.append(f'<button onclick="act(\'{item_id}\',\'ready\')">إرسال للمراجعة</button>')
        if status == "READY_FOR_REVIEW":
            out.append(f'<button onclick="act(\'{item_id}\',\'approve\')">اعتماد</button>')
            out.append(f'<button onclick="act(\'{item_id}\',\'reject\')">رفض</button>')
        if item_id.startswith("opp-"):
            out.append(f'<button onclick="act(\'{item_id}\',\'regenerate_offer\')">إعادة توليد العرض</button>')
        return "".join(out)
    services = "".join(
        f'<article><div class="row"><b>{esc(x.get("title"))}</b><span>{esc(x.get("status"))}</span></div>'
        f'<p>{esc(x.get("description"))}</p><div class="muted">المخرجات</div><ul>{"".join(f"<li>{esc(v)}</li>" for v in x.get("deliverables", []))}</ul>'
        f'<div class="actions">{buttons(x)}</div></article>' for x in state.get("services", [])) or '<article>لا توجد خدمات.</article>'
    opportunities = "".join(
        f'<article><div class="row"><b>{esc(x.get("title"))}</b><span>{int(x.get("match_score",0))}%</span></div>'
        f'<p>{esc(x.get("description"))}</p><p><b>السعر:</b> {int(x.get("suggested_price_egp",0))} جنيه · <b>المدة:</b> {int(x.get("suggested_days",0))} أيام</p>'
        f'<details><summary>العرض الجاهز</summary><pre>{esc(x.get("offer", ""))}</pre></details><div class="actions">{buttons(x)}</div></article>'
        for x in state.get("opportunities", [])) or '<article>لا توجد فرص.</article>'
    activity = "".join(f'<li>{esc(x.get("time"))} — {esc(x.get("message"))}</li>' for x in state.get("activity", [])[:20])
    return f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-store"><title>Khyrat Marketplace Control Center</title><style>
body{{font-family:Arial,Tahoma,sans-serif;background:#f3f5f7;color:#20242a;margin:0}}.wrap{{max-width:1200px;margin:auto;padding:24px}}header{{background:#fff;border:1px solid #ddd;border-radius:16px;padding:20px;margin-bottom:14px}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.stat,section,article{{background:#fff;border:1px solid #ddd;border-radius:14px;padding:16px}}.stat b{{font-size:28px;display:block;margin-top:6px}}section{{margin-top:14px}}.items{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.row{{display:flex;justify-content:space-between;gap:12px}}.muted{{color:#66717d}}button{{border:1px solid #c9ced5;background:#f7f8fa;border-radius:8px;padding:8px 12px;cursor:pointer}}button:hover{{background:#e9edf1}}.actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}pre{{white-space:pre-wrap;background:#f5f6f8;padding:12px;border-radius:8px;line-height:1.7}}#msg{{position:fixed;bottom:18px;left:18px;background:#20242a;color:#fff;padding:10px 14px;border-radius:10px;display:none}}@media(max-width:800px){{.grid,.items{{grid-template-columns:1fr}}}}</style></head><body><div class="wrap"><header><h1>Khyrat Marketplace Control Center</h1><p class="muted">لوحة خاصة على جهازك — لا يوجد نشر تلقائي على خمسات أو مستقل.</p><button onclick="location.reload()">تحديث</button></header><div class="grid"><div class="stat">الخدمات<b>{m['services']}</b></div><div class="stat">Portfolio<b>{m['portfolio']}</b></div><div class="stat">فرص مستقل<b>{m['opportunities']}</b></div><div class="stat">بانتظار قرارك<b>{m['review_queue']}</b></div></div><section><h2>خدمات خمسات</h2><div class="items">{services}</div></section><section><h2>فرص مستقل والعروض</h2><div class="items">{opportunities}</div></section><section><h2>Activity Log</h2><ul>{activity or '<li>لا يوجد نشاط</li>'}</ul></section><section><h2>الوضع الأمني</h2><p>اللوحة مربوطة بـ 127.0.0.1 فقط. بيانات Marketplace لا يتم نشرها على GitHub Pages. بيانات الدخول للمنصات غير موجودة في الواجهة.</p></section></div><div id="msg"></div><script>
async function act(id, action){{const r=await fetch('/api/action',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id,action}})}});const d=await r.json();const m=document.getElementById('msg');m.textContent=d.message||d.error||'تم';m.style.display='block';setTimeout(()=>location.reload(),500);}}
</script></body></html>'''


def handle_action(payload: dict) -> tuple[bool, str]:
    state = load_state()
    item_id = payload.get("id", "")
    action = payload.get("action", "")
    collections = [state.get("services", []), state.get("opportunities", [])]
    item = next((x for group in collections for x in group if x.get("id") == item_id), None)
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
    state.setdefault("activity", []).insert(0, {"time": result.reviewed_at if result else "now", "message": f"{action}: {item_id}"})
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

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, html(load_state()))
        elif path == "/api/state":
            self._send(200, json.dumps(load_state(), ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/api/health":
            self._send(200, json.dumps({"ok": True, "data_file": str(DATA_FILE)}, ensure_ascii=False), "application/json; charset=utf-8")
        else:
            self._send(404, "Not Found")

    def do_POST(self):
        if urlparse(self.path).path != "/api/action":
            self._send(404, json.dumps({"error": "Not Found"}), "application/json; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            ok, message = handle_action(payload)
            self._send(200 if ok else 400, json.dumps({"ok": ok, "message": message, "error": None if ok else message}, ensure_ascii=False), "application/json; charset=utf-8")
        except Exception as exc:
            self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), "application/json; charset=utf-8")

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
        save_state(state)
    server = ThreadingHTTPServer((HOST, args.port), Handler)
    print(f"Khyrat Marketplace Control Center: http://{HOST}:{args.port}")
    print("Private: listening on localhost only. Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
