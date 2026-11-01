from __future__ import annotations

import csv
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

from blogger_search_console_prioritizer import prioritize
from blogger_seo_audit import run as run_public_audit
from config import _service_account_info
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

BLOG_URL = "https://askmahmoudkhyrat.blogspot.com/"
CAIRO = ZoneInfo("Africa/Cairo")
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def _gsc_service():
    info = _service_account_info()
    credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


def _query(service, site: str, start: str, end: str, dimensions: list[str]) -> list[dict[str, Any]]:
    response = service.searchanalytics().query(
        siteUrl=site,
        body={
            "startDate": start,
            "endDate": end,
            "dimensions": dimensions,
            "rowLimit": 25000,
            "dataState": "final",
        },
    ).execute()
    result = []
    for row in response.get("rows", []) or []:
        keys = row.get("keys", [])
        item = {
            "clicks": float(row.get("clicks", 0) or 0),
            "impressions": float(row.get("impressions", 0) or 0),
            "ctr": float(row.get("ctr", 0) or 0),
            "position": float(row.get("position", 0) or 0),
        }
        for index, dimension in enumerate(dimensions):
            item[dimension] = str(keys[index]) if index < len(keys) else ""
        result.append(item)
    return result


def build_growth_snapshot(audit: dict, page_rows: list[dict], query_rows: list[dict], start: str, end: str) -> dict:
    page_metrics = [
        {
            "url": row.get("page", ""),
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": row.get("ctr", 0),
            "position": row.get("position", 0),
        }
        for row in page_rows if row.get("page")
    ]
    priorities = prioritize(audit, page_metrics, limit=250)
    query_opportunities = []
    for row in query_rows:
        impressions = float(row.get("impressions", 0) or 0)
        ctr = float(row.get("ctr", 0) or 0)
        position = float(row.get("position", 0) or 0)
        if impressions < 1:
            continue
        reasons = []
        if impressions >= 10 and ctr < 0.02:
            reasons.append("LOW_CTR")
        if 4 <= position <= 20:
            reasons.append("STRIKING_DISTANCE")
        if reasons:
            query_opportunities.append({
                **row,
                "ctr_percent": round(ctr * 100, 2),
                "reasons": reasons,
            })
    query_opportunities.sort(
        key=lambda row: (
            -len(row["reasons"]),
            -float(row.get("impressions", 0)),
            float(row.get("position", 0)),
        )
    )
    total_clicks = sum(float(row.get("clicks", 0) or 0) for row in page_rows)
    total_impressions = sum(float(row.get("impressions", 0) or 0) for row in page_rows)
    return {
        "generated_at": datetime.now(CAIRO).isoformat(),
        "site": os.getenv("SEARCH_CONSOLE_SITE_URL", BLOG_URL).strip(),
        "period": {"start": start, "end": end, "data_state": "final"},
        "measurement": {
            "pages_with_data": len(page_rows),
            "queries_with_data": len(query_rows),
            "clicks": round(total_clicks, 2),
            "impressions": round(total_impressions, 2),
            "ctr": round(total_clicks / total_impressions, 4) if total_impressions else 0,
            "query_opportunities": len(query_opportunities),
            "page_opportunities": sum(1 for item in priorities["priorities"] if any(reason in item["reasons"] for reason in ("HIGH_IMPRESSIONS_LOW_CTR", "RANKING_NEAR_PAGE_ONE"))),
            "pages_in_technical_backlog": sum(1 for item in priorities["priorities"] if any(reason != "NO_SEARCH_CONSOLE_ROW" for reason in item["reasons"])),
        },
        "important_limit": (
            "Search Console reports sampled/available performance rows, not a complete index inventory. "
            "No query rows means no query-level opportunity can be inferred; it does not prove that no searches exist."
        ),
        "technical_audit_summary": audit.get("summary", {}),
        "page_priorities": priorities,
        "query_opportunities": query_opportunities[:250],
        "page_metrics": page_rows,
        "query_metrics": query_rows,
    }


def main() -> int:
    site = os.getenv("SEARCH_CONSOLE_SITE_URL", BLOG_URL).strip()
    if not site:
        raise RuntimeError("SEARCH_CONSOLE_SITE_URL is empty.")
    days = max(7, min(90, int(os.getenv("SEARCH_CONSOLE_DAYS", "28"))))
    cairo_today = datetime.now(CAIRO).date()
    end_date = cairo_today - timedelta(days=2)
    start_date = end_date - timedelta(days=days - 1)
    service = _gsc_service()
    page_rows = _query(service, site, start_date.isoformat(), end_date.isoformat(), ["page"])
    query_rows = _query(service, site, start_date.isoformat(), end_date.isoformat(), ["query", "page"])
    audit = json.loads(Path("artifacts/seo-audit/report.json").read_text(encoding="utf-8"))
    snapshot = build_growth_snapshot(
        audit, page_rows, query_rows, start_date.isoformat(), end_date.isoformat()
    )
    out = Path("artifacts/seo-audit")
    out.mkdir(parents=True, exist_ok=True)
    (out / "search-console-growth.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out / "search-console-pages.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["page", "clicks", "impressions", "ctr", "position"])
        writer.writeheader()
        writer.writerows(page_rows)
    (out / "growth-priorities.json").write_text(
        json.dumps(snapshot["page_priorities"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(snapshot["measurement"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
