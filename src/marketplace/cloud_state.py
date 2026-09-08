"""Optional Cloudflare D1 state backend for serverless Marketplace deployments.

The existing local JSON store remains the default. When D1 credentials are
present, the Vercel adapter uses one JSON document in a single D1 row, keeping
Marketplace business logic unchanged.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
_DATABASE_ID = os.getenv("CLOUDFLARE_D1_DATABASE_ID", "").strip()
_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()


def configured() -> bool:
    return bool(_ACCOUNT_ID and _DATABASE_ID and _API_TOKEN)


def _query(sql: str, params: list[str] | None = None) -> dict[str, Any]:
    if not configured():
        raise RuntimeError("Cloudflare D1 is not configured")
    url = f"https://api.cloudflare.com/client/v4/accounts/{_ACCOUNT_ID}/d1/database/{_DATABASE_ID}/query"
    body = json.dumps({"sql": sql, "params": params or []}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {_API_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"D1 request failed ({exc.code}): {detail[:500]}") from exc
    if not payload.get("success"):
        raise RuntimeError(f"D1 request failed: {payload}")
    return payload


def ensure_schema() -> None:
    _query("CREATE TABLE IF NOT EXISTS marketplace_state (id INTEGER PRIMARY KEY, state_json TEXT NOT NULL)")


def load_state() -> dict[str, Any]:
    ensure_schema()
    result = _query("SELECT state_json FROM marketplace_state WHERE id = 1")
    rows = result.get("result", [{}])[0].get("results", [])
    if not rows:
        return {"updated_at": "", "services": [], "portfolio": [], "opportunities": [], "activity": []}
    return json.loads(rows[0]["state_json"])


def save_state(state: dict[str, Any]) -> None:
    ensure_schema()
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    _query(
        "INSERT INTO marketplace_state (id, state_json) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET state_json = excluded.state_json",
        [raw],
    )
