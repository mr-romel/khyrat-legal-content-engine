from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import _service_account_info, load_video_config
from sheets import create_service

CAIRO = ZoneInfo("Africa/Cairo")
DEFAULT_PROPERTY_ID = "497002086"
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
METRICS = [
    "activeUsers", "newUsers", "sessions", "engagementRate",
    "averageSessionDuration", "screenPageViews", "eventCount", "keyEvents",
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
                dimensions: list[str] | None = None, limit: int = 100,
                metrics: list[str] | None = None) -> dict:
    requested_metrics = metrics or METRICS
    body: dict[str, Any] = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "metrics": [{"name": name} for name in requested_metrics],
        "limit": limit,
    }
    if dimensions:
        body["dimensions"] = [{"name": name} for name in dimensions]
    return service.properties().runReport(
        property=f"properties/{property_id}", body=body
    ).execute()


def _metric_map(response: dict, metric_names: list[str] | None = None) -> dict[str, float | None]:
    requested_metrics = metric_names or METRICS
    headers = [x.get("name", "") for x in response.get("metricHeaders", [])]
    rows = response.get("rows", []) or []
    if not rows:
        return {name: None for name in requested_metrics}
    values = rows[0].get("metricValues", []) or []
    output = {}
    for name in requested_metrics:
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

    def report(start: date, end: date, dims: list[str] | None = None, limit: int = 100,
               metrics: list[str] | None = None):
        return _run_report(service, property_id, start.isoformat(), end.isoformat(), dims, limit, metrics)

    current = report(current_start, current_end)
    previous = report(previous_start, previous_end)
    channels = report(current_start, current_end, ["sessionDefaultChannelGroup"], 50,
                       ["activeUsers", "sessions", "engagementRate"])
    pages = report(current_start, current_end, ["pagePathPlusQueryString"], 100,
                    ["activeUsers", "sessions", "screenPageViews", "keyEvents"])
    events = report(current_start, current_end, ["eventName"], 100,
                    ["eventCount", "keyEvents"])

    current_metrics = _metric_map(current)
    previous_metrics = _metric_map(previous)
    deltas = {}
    for key, value in current_metrics.items():
        old = previous_metrics.get(key)
        deltas[key] = round(value - old, 4) if value is not None and old is not None else None

    return {
        "generated_at": datetime.now(CAIRO).isoformat(),
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


LEAD_SHEET_NAME = os.getenv("GA4_LEAD_SHEET_NAME", "Lead CRM").strip()
LEAD_HEADERS = [
    "lead_ref", "received_at", "source_platform", "source_campaign", "landing_page",
    "contact_method", "service_type", "lead_status", "first_response_at",
    "consultation_booked_at", "client_confirmed_at", "owner", "next_action", "notes",
]
CONFIRMED_STATUSES = {"QUALIFIED", "CONSULTATION_BOOKED", "CLIENT"}


def _ensure_lead_sheet(sheets, spreadsheet_id: str) -> None:
    metadata = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
    sheet_properties = next(
        (item.get("properties", {}) for item in metadata.get("sheets", [])
         if str(item.get("properties", {}).get("title", "")).casefold() == LEAD_SHEET_NAME.casefold()),
        None,
    )
    if not sheet_properties:
        created = sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": LEAD_SHEET_NAME}}}]},
        ).execute()
        sheet_properties = next(
            (item.get("addSheet", {}).get("properties", {}) for item in created.get("replies", [])
             if item.get("addSheet", {}).get("properties")),
            {},
        )
    sheet_id = sheet_properties.get("sheetId")
    if sheet_id is not None:
        validations = [
            (2, 3, ["GOOGLE_ORGANIC", "GOOGLE_ADS", "FACEBOOK", "INSTAGRAM", "LINKEDIN", "YOUTUBE", "DIRECT", "REFERRAL", "OTHER"]),
            (5, 6, ["WHATSAPP", "PHONE", "WEBSITE_FORM", "FACEBOOK", "LINKEDIN", "YOUTUBE", "OTHER"]),
            (7, 8, ["NEW", "CONTACTED", "QUALIFIED", "CONSULTATION_BOOKED", "CLIENT", "LOST"]),
        ]
        requests = []
        for start_col, end_col, values in validations:
            requests.append({"setDataValidation": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000,
                          "startColumnIndex": start_col, "endColumnIndex": end_col},
                "rule": {"condition": {"type": "ONE_OF_LIST",
                                       "values": [{"userEnteredValue": value} for value in values]},
                         "strict": True, "showCustomUi": True},
            }})
        requests.append({"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }})
        requests.append({"updateCells": {
            "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
            "rows": [
                {"values": [{"note": "One row per real inquiry received. Do not count website visits or button clicks as leads. Avoid storing names, phone numbers, case documents or other personal data in this reporting tab."}]},
                {"values": [{"note": "Use Cairo local date/time when the inquiry was first received."}]},
                {"values": [{"note": "Choose the originating platform/channel. Use GOOGLE_ORGANIC for unpaid Google Search."}]},
                {"values": [{"note": "Optional campaign/source detail such as campaign name or UTM campaign."}]},
                {"values": [{"note": "Internal Blogger page URL where the inquiry originated, if known."}]},
                {"values": [{"note": "Allowed values: WHATSAPP, PHONE, WEBSITE_FORM, FACEBOOK, LINKEDIN, YOUTUBE, OTHER."}]},
                {"values": [{"note": "Use the legal service category; avoid adding client-identifying details."}]},
                {"values": [{"note": "Allowed values: NEW, CONTACTED, QUALIFIED, CONSULTATION_BOOKED, CLIENT, LOST. CLIENT is counted only after engagement is confirmed."}]},
            ],
            "fields": "note",
        }})
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()
    current = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{LEAD_SHEET_NAME}!A1:N1"
    ).execute().get("values", [])
    if not current or current[0][:len(LEAD_HEADERS)] != LEAD_HEADERS:
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"{LEAD_SHEET_NAME}!A1:N1",
            valueInputOption="RAW", body={"values": [LEAD_HEADERS]},
        ).execute()


def summarize_leads(rows: list[list[str]]) -> dict:
    status_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}
    total = 0
    confirmed = 0
    clients = 0
    pending = 0
    for row in rows:
        values = {name: (str(row[index]).strip() if index < len(row) else "") for index, name in enumerate(LEAD_HEADERS)}
        if not any(values.get(key) for key in ("lead_ref", "received_at", "contact_method", "service_type")):
            continue
        total += 1
        status = values.get("lead_status", "").upper() or "UNCLASSIFIED"
        source = values.get("source_platform", "").strip() or "UNKNOWN"
        method = values.get("contact_method", "").strip() or "UNKNOWN"
        status_counts[status] = status_counts.get(status, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1
        method_counts[method] = method_counts.get(method, 0) + 1
        if status in CONFIRMED_STATUSES:
            confirmed += 1
        if status == "CLIENT":
            clients += 1
        if status in {"NEW", "CONTACTED", "UNCLASSIFIED"}:
            pending += 1
    return {
        "status": "CONNECTED",
        "inquiries_received": total,
        "qualified_leads": confirmed,
        "clients_confirmed": clients,
        "pending_follow_up": pending,
        "by_status": dict(sorted(status_counts.items())),
        "by_source_platform": dict(sorted(source_counts.items())),
        "by_contact_method": dict(sorted(method_counts.items())),
        "definition": (
            "CRM rows only. A website visit or GA4 contact click is not a lead. "
            "Qualified leads are statuses QUALIFIED, CONSULTATION_BOOKED, or CLIENT; "
            "clients are counted only when status is CLIENT."
        ),
    }


def read_lead_summary() -> dict:
    cfg = load_video_config()
    sheets = create_service(cfg["service_account_info"])
    _ensure_lead_sheet(sheets, cfg["sheet_id"])
    values = sheets.spreadsheets().values().get(
        spreadsheetId=cfg["sheet_id"], range=f"{LEAD_SHEET_NAME}!A2:N"
    ).execute().get("values", [])
    return summarize_leads(values)


def main() -> int:
    property_id = os.getenv("GA4_PROPERTY_ID", DEFAULT_PROPERTY_ID).strip()
    if not property_id.isdigit():
        raise ValueError("GA4_PROPERTY_ID must be a numeric GA4 property ID.")
    today = datetime.now(CAIRO).date()
    end_date = today - timedelta(days=1)
    service = _analytics_service()
    snapshot = build_snapshot(service, property_id, end_date)
    snapshot["lead_crm"] = read_lead_summary()
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
        "lead_crm": snapshot["lead_crm"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
