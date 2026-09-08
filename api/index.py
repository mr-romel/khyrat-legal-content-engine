from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from marketplace import server
from marketplace_mvp import load_state as local_load_state, save_state as local_save_state
from marketplace.cloud_state import configured as d1_configured
from marketplace.cloud_state import load_state as d1_load_state, save_state as d1_save_state


USE_D1 = d1_configured()


def _load_state():
    return d1_load_state() if USE_D1 else local_load_state()


def _save_state(state):
    return d1_save_state(state) if USE_D1 else local_save_state(state)


# server.py owns the Marketplace workflow. Patch only its persistence boundary;
# the existing local server and business logic remain unchanged.
server.load_state = _load_state
server.save_state = _save_state


def _response(handler: BaseHTTPRequestHandler, status: int, payload, content_type="application/json; charset=utf-8"):
    body = payload if isinstance(payload, bytes) else (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if not isinstance(payload, str) else payload.encode("utf-8")
    )
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _state():
    return _load_state()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                return _response(self, 200, {"ok": True, "service": "khyrat-marketplace", "runtime": "vercel", "persistence": "d1" if USE_D1 else "local-fallback"})
            if path == "/api/state":
                return _response(self, 200, _state())
            if path == "/":
                return _response(self, 200, server.render_dashboard(_state()), "text/html; charset=utf-8")
            return _response(self, 404, {"ok": False, "error": "not_found"})
        except Exception as exc:
            return _response(self, 500, {"ok": False, "error": str(exc)})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {"/api/action", "/api/opportunity"}:
            return _response(self, 404, {"ok": False, "error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")

            if path == "/api/action":
                ok, message = server.handle_action(payload)
                return _response(self, 200 if ok else 400, {"ok": ok, "message": message, "error": None if ok else message})

            title = str(payload.get("title", "")).strip()
            description = str(payload.get("description", "")).strip()
            source_url = str(payload.get("source_url", "")).strip()
            if not title or not description:
                raise ValueError("العنوان والوصف مطلوبان")
            price = int(payload.get("price_usd", 5))
            days = int(payload.get("days", 3))
            if price < 5 or price % 5:
                raise ValueError("سعر مستقل يجب أن يكون 5$ أو مضاعفاته")
            if days < 1:
                raise ValueError("المدة يجب أن تكون يومًا واحدًا على الأقل")

            state = _load_state()
            item = server.ingest_mostaql_opportunity(state, title, description, source_url)
            item["suggested_price_usd"] = price
            item["suggested_price_egp"] = price * 50
            item["suggested_days"] = days
            item["notes"] = str(payload.get("notes", "")).strip()
            item["offer"] = server.build_offer(item)
            item["status"] = item["lifecycle"] = "OFFER_READY"
            server.log_activity(state, f"إضافة فرصة يدويًا: {title}")
            _save_state(state)
            return _response(self, 200, {"ok": True, "message": f"تمت إضافة الفرصة — المطابقة {item.get('match_score', 0)}%", "opportunity": item})
        except Exception as exc:
            return _response(self, 400, {"ok": False, "error": str(exc)})

    def log_message(self, fmt, *args):
        return
