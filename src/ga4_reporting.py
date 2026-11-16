from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import _service_account_info

CAIRO = ZoneInfo("Africa/Cairo")
DEFAULT_PROPERTY_ID = "497002086"
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
METRICS = [
    "activeUsers", "newUsers", "sessions", "engagementRate",
    "averageSessionDuration", "screenPageViews", "eventCount",
]


def _analytics_service():
    credentials = Credentials.from_service_account_info(
        _service_account_info(), scopes=SCOPES
    )
    return build("analyticsdata", "v1beta", credentials=credentials, cache_discovery=False)


def _value(row: dict[str, Any], index: int) -> float | None:
    values = row.get("metricValues", []) or []
    if index >= len(values):
        return None
    raw = values[index].get("value")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _run_report(service, property_id: str, start: str, end: str,
                dimensions: list[str] | None = None, limit: int = 100) -> dict:
    body: dict[str, Any] = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "metrics": [{"name": name} for name in METRICS],
        "limit": limit,
    }
    if dimensions:
        body["dimensions"] = [{"name": name} for name in dimensions]
    return service.properties().runReport(
        name=f"properties/{property_id}", body=body
    ).execute()


def _metric_map(response: dict) -> dict[str, float | None]:
    headers = [x.get("name", "") for x in response.get("metricHeaders", [])]
    rows = response.get("rows", []) or []
    if not rows:
        return {name: None for name in METRICS}
    values = rows[0].get("metricValues", []) or []
    output = {}
    for name in METRICS:
        try:
            index = headers.index(name)
            output[name] = _value({"metricValues": values}, index)
        except ValueError:
            output[name] = None
    return output


def _dimension_rows(response: dict, dimensions: list[str]) -> list[dict]:
    dim_headers = [x.get("name", "") for x in response.get("dimensionHeaders", [])]
    metric_headers = [x.get("name", "") for x in response.get("metricHeaders", [])]
    output = []
    for row in response.get("rows", []) or []:
        item = {}
        for index, name in enumerate(dim_headers):
            vals = row.get("dimensionValues", []) or []
            item[name or (dimensions[index] if index < len(dimensions) else f"dimension_{index}")] = (
                vals[index].get("value", "") if index < len(vals) else ""
            )
        for index, name in enumerate(metric_headers):
            item[name] = _value(row, index)
        output.append(item)
    return output


def build_snapshot(service, property_id: str, end_date: date) -> dict:
    """Compare two complete seven-day windows; never turn a missing API response into zero."""
    current_end = end_date
    current_start = current_end - timedelta(days=6)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)

    def report(start: date, end: date, dims: list[str] | None = None, limit: int = 100):
        return _run_report(service, property_id, start.isoformat(), end.isoformat(), dims, limit)

    current = report(current_start, current_end)
    previous = report(previous_start, previous_end)
    channels = report(current_start, current_end, ["sessionDefaultChannelGroup"], 50)
    pages = report(current_start, current_end, ["pagePathPlusQueryString"], 100)
    events = report(current_start, current_end, ["eventName"], 100)

    current_metrics = _metric_map(current)
    previous_metrics = _metric_map(previous)
    deltas = {}
    for key, value in current_metrics.items():
        old = previous_metrics.get(key)
        deltas[key] = round(value - old, 4) if value is not None and old is not None else None

    return {
        "generated_at": date.today().isoformat(),
        "property_id": str(property_id),
        "site": os.getenv("GA4_SITE_URL", "https://askmahmoudkhyrat.blogspot.com/"),
        "status": "OK" if current.get("rows") is not None and previous.get("rows") is not None else "PARTIAL",
        "period": {"start": current_start.isoformat(), "end": current_end.isoformat()},
        "previous_period": {"start": previous_start.isoformat(), "end": previous_end.isoformat()},
        "current": {"has_rows": bool(current.get("rows")), "metrics": current_metrics},
        "previous": {"has_rows": bool(previous.get("rows")), "metrics": previous_metrics},
        "delta": deltas,
        "channels": _dimension_rows(channels, ["sessionDefaultChannelGroup"]),
        "top_pages": _dimension_rows(pages, ["pagePathPlusQueryString"]),
        "events": _dimension_rows(events, ["eventName"]),
        "interpretation_limit": (
            "A missing metrics row is represented as null, not zero. GA4 page metrics are not query-level "
            "Search Console attribution. Key-event counts are not confirmed clients."
        ),
    }


def main() -> int:
    property_id = os.getenv("GA4_PROPERTY_ID", DEFAULT_PROPERTY_ID).strip()
    if not property_id.isdigit():
        raise ValueError("GA4_PROPERTY_ID must be a numeric GA4 property ID.")
    today = date.today()
    end_date = today - timedelta(days=1)
    service = _analytics_service()
    snapshot = build_snapshot(service, property_id, end_date)
    out = Path(os.getenv("GA4_REPORT_DIR", "artifacts/ga4"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "weekly-report.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "property_id": property_id,
        "period": snapshot["period"],
        "previous_period": snapshot["previous_period"],
        "current": snapshot["current"],
        "previous": snapshot["previous"],
        "delta": snapshot["delta"],
        "top_pages": snapshot["top_pages"][:10],
        "channels": snapshot["channels"],
        "events": snapshot["events"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
