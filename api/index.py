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
from marketplace.ai_media import generate_khamsat_image, generate_offer, image_data_url, offer_terms
from marketplace.cloud_state import configured as d1_configured
from marketplace.cloud_state import load_state as d1_load_state, save_state as d1_save_state
from marketplace.live import fetch_mostaql_projects
from marketplace.pipeline import ensure_initial_assets, ingest_mostaql_opportunity
from marketplace.web_dashboard import render as render_live_dashboard
from marketplace_mvp import load_state as local_load_state, save_state as local_save_state

USE_D1 = d1_configured()
GEMINI_CONFIGURED = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
HANDLED_STATUSES = {"SUBMITTED", "IGNORED", "REJECTED"}


def _load_state():
    return d1_load_state() if USE_D1 else local_load_state()


def _save_state(state):
    return d1_save_state(state) if USE_D1 else local_save_state(state)


server.load_state = _load_state
server.save_state = _save_state


def _response(handler: BaseHTTPRequestHandler, status: int, payload, content_type="application/json; charset=utf-8"):
    body = payload if isinstance(payload, bytes) else (json.dumps(payload, ensure_ascii=False).encode("utf-8") if not isinstance(payload, str) else payload.encode("utf-8"))
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    # GitHub Pages hosts the frontend on a different origin than Vercel.
    # Allow the dashboard to call the API and preflight POST requests.
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def _state_with_assets():
    state = _load_state()
    changed = ensure_initial_assets(state)
    if any(changed.values()):
        _save_state(state)
    return state


def _status(item: dict) -> str:
    return str(item.get("lifecycle", item.get("status", "NEW"))).upper()


def _mark_opportunity(state: dict, opportunity_id: str, status: str) -> dict:
    if status not in HANDLED_STATUSES:
        raise ValueError("الحالة غير مدعومة")
    item = next((x for x in state.get("opportunities", []) if str(x.get("id")) == opportunity_id), None)
    if not item:
        raise ValueError("الفرصة غير موجودة")
    item["status"] = item["lifecycle"] = status
    item["handled_at"] = server._now()
    labels = {"SUBMITTED": "تم التقديم على فرصة مستقل", "IGNORED": "تم تجاهل فرصة مستقل", "REJECTED": "تم تسجيل رفض فرصة مستقل"}
    state.setdefault("activity", []).insert(0, {"time": server._now(), "message": f"{labels[status]}: {item.get('title', '')}"})
    state["activity"] = state["activity"][:100]
    _save_state(state)
    return item


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        return _response(self, 204, b"", "text/plain; charset=utf-8")

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                return _response(self, 200, {"ok": True, "service": "khyrat-marketplace", "runtime": "vercel", "persistence": "d1" if USE_D1 else "local-fallback", "live_mostaql": True, "gemini_offers": GEMINI_CONFIGURED, "khamsat_images": GEMINI_CONFIGURED})
            if path == "/api/state":
                return _response(self, 200, _state_with_assets())
            if path == "/":
                return _response(self, 200, render_live_dashboard(_state_with_assets()), "text/html; charset=utf-8")
            return _response(self, 404, {"ok": False, "error": "not_found"})
        except Exception as exc:
            return _response(self, 500, {"ok": False, "error": str(exc)})

    def do_POST(self):
        path = urlparse(self.path).path
        allowed = {"/api/action", "/api/opportunity", "/api/mostaql/sync", "/api/mostaql/offer", "/api/khamsat/image", "/api/marketplace/opportunity-status"}
        if path not in allowed:
            return _response(self, 404, {"ok": False, "error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")

            if path == "/api/marketplace/opportunity-status":
                item = _mark_opportunity(_load_state(), str(payload.get("id", "")).strip(), str(payload.get("status", "")).upper())
                return _response(self, 200, {"ok": True, "opportunity": item})

            if path == "/api/action":
                ok, message = server.handle_action(payload)
                return _response(self, 200 if ok else 400, {"ok": ok, "message": message, "error": None if ok else message})

            if path == "/api/mostaql/sync":
                limit = int(payload.get("limit", 12) or 12)
                projects = fetch_mostaql_projects(limit=limit)
                state = _load_state()
                added = 0
                updated = 0
                skipped = 0
                for project in projects:
                    title = project["title"]
                    description = project["description"]
                    existing = next((x for x in state.get("opportunities", []) if str(x.get("platform", "mostaql")).lower() == "mostaql" and x.get("title", "").strip().lower() == title.strip().lower()), None)
                    if existing and _status(existing) in HANDLED_STATUSES:
                        skipped += 1
                        continue
                    before = len(state.get("opportunities", []))
                    item = ingest_mostaql_opportunity(state, title, description, project["source_url"])
                    item["match_score"] = project["match_score"]
                    item["acquisition_score"] = project["acquisition_score"]
                    item["rationale"] = project["rationale"]
                    item["ranking_reasons"] = project["rationale"]
                    if len(state.get("opportunities", [])) > before:
                        added += 1
                    else:
                        updated += 1
                state.setdefault("activity", []).insert(0, {"time": server._now(), "message": f"تم سحب {len(projects)} فرصة من مستقل — جديد {added} / محدث {updated} / مستبعد {skipped}"})
                state["activity"] = state["activity"][:100]
                _save_state(state)
                return _response(self, 200, {"ok": True, "message": f"تم سحب {len(projects)} فرصة — جديد {added}، محدث {updated}، مستبعد {skipped}", "projects": projects, "skipped": skipped})

            if path == "/api/mostaql/offer":
                if not GEMINI_CONFIGURED:
                    raise ValueError("أضف GEMINI_API_KEY إلى Vercel Environment Variables أولًا")
                opportunity_id = str(payload.get("id", "")).strip()
                state = _load_state()
                item = next((x for x in state.get("opportunities", []) if str(x.get("id")) == opportunity_id), None)
                if not item:
                    raise ValueError("الفرصة غير موجودة")
                price, days = offer_terms(item)
                item["suggested_price_usd"] = price
                item["suggested_days"] = days
                offer = generate_offer(item)
                item["offer"] = offer
                item["status"] = item["lifecycle"] = "OFFER_READY"
                state.setdefault("activity", []).insert(0, {"time": server._now(), "message": f"Gemini أعاد دراسة عرض: {item.get('title', '')} — ${price} / {days} أيام"})
                state["activity"] = state["activity"][:100]
                _save_state(state)
                return _response(self, 200, {"ok": True, "offer": offer, "price_usd": price, "days": days, "opportunity": item})

            if path == "/api/khamsat/image":
                if not GEMINI_CONFIGURED:
                    raise ValueError("أضف GEMINI_API_KEY إلى Vercel Environment Variables أولًا")
                service_id = str(payload.get("id", "")).strip()
                state = _load_state()
                service = next((x for x in state.get("services", []) if str(x.get("id")) == service_id), None)
                if not service:
                    raise ValueError("الخدمة غير موجودة")
                image = generate_khamsat_image(service)
                return _response(self, 200, {"ok": True, "image_data_url": image_data_url(image), "width": 1700, "height": 970, "format": "JPEG", "service": service})

            title = str(payload.get("title", "")).strip()
            description = str(payload.get("description", "")).strip()
            source_url = str(payload.get("source_url", "")).strip()
            if not title or not description:
                raise ValueError("العنوان والوصف مطلوبان")
            price = int(payload.get("price_usd", 5)); days = int(payload.get("days", 3))
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
