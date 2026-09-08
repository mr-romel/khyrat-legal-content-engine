from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from marketplace import server
from marketplace_mvp import load_state, save_state


def _response(handler: BaseHTTPRequestHandler, status: int, payload, content_type="application/json; charset=utf-8"):
    body = payload if isinstance(payload, bytes) else (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if not isinstance(payload, str) else payload.encode("utf-8")
    )
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _state():
    return load_state()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return _response(self, 200, {"ok": True, "service": "khyrat-marketplace", "runtime": "vercel"})
        if path == "/api/state":
            return _response(self, 200, _state())
        if path == "/":
            try:
                html = server.render_dashboard(_state())
            except TypeError:
                html = server.render_dashboard()
            return _response(self, 200, html, "text/html; charset=utf-8")
        return _response(self, 404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {"/api/action", "/api/opportunity"}:
            return _response(self, 404, {"ok": False, "error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            return _response(self, 400, {"ok": False, "error": f"invalid_json: {exc}"})
        return _response(self, 501, {"ok": False, "error": "vercel_adapter_pending", "received": payload})

    def log_message(self, fmt, *args):
        return
