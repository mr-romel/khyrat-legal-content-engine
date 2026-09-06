from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from content_system import SYSTEM_SHEETS, build_authority_rows, ensure_system_sheets, update_winner
from post_bank import get_bank_rows
from sheets import create_service, get_values


def _rows(service, spreadsheet_id: str, sheet: str, headers: list[str]) -> list[dict[str, str]]:
    values = get_values(service, spreadsheet_id, f"{sheet}!A:Z")
    if len(values) <= 1:
        return []
    result = []
    for raw in values[1:]:
        padded = list(raw) + [""] * (len(headers) - len(raw))
        result.append({headers[i]: str(padded[i]) for i in range(len(headers))})
    return result


def _metric_rows(service, spreadsheet_id: str) -> list[dict[str, str]]:
    return _rows(service, spreadsheet_id, "ContentMetrics", SYSTEM_SHEETS["ContentMetrics"])


def _number(row: dict[str, str], key: str) -> float:
    try:
        return float(str(row.get(key, "0") or "0").replace(",", ""))
    except ValueError:
        return 0.0


def _baseline(metrics: list[dict[str, str]]) -> dict[str, float]:
    keys = {"Reach": "reach", "Impressions": "impressions", "Reactions": "reactions", "Comments": "comments", "Shares": "shares", "Saves": "saves", "Clicks": "clicks", "Leads": "leads"}
    if not metrics:
        return {v: 0.0 for v in keys.values()}
    return {dst: sum(_number(row, src) for row in metrics) / len(metrics) for src, dst in keys.items()}


def main() -> None:
    service_account_raw = __import__("os").getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not service_account_raw:
        raise RuntimeError("Missing required environment variable: GOOGLE_SERVICE_ACCOUNT_JSON")
    try:
        service_account_info = json.loads(service_account_raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON.") from exc
    if not isinstance(service_account_info, dict):
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON must be a JSON object.")

    spreadsheet_id = __import__("os").getenv("GOOGLE_SHEET_ID", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("Missing required environment variable: GOOGLE_SHEET_ID")

    service = create_service(service_account_info)
    ensure_system_sheets(service, spreadsheet_id)
    metrics = _metric_rows(service, spreadsheet_id)
    if metrics:
        baseline = _baseline(metrics)
        for row in metrics[-100:]:
            post_id = row.get("Post ID", "").strip()
            if not post_id:
                continue
            metric_map = {
                "reach": _number(row, "Reach"), "impressions": _number(row, "Impressions"),
                "reactions": _number(row, "Reactions"), "comments": _number(row, "Comments"),
                "shares": _number(row, "Shares"), "saves": _number(row, "Saves"),
                "clicks": _number(row, "Clicks"), "leads": _number(row, "Leads"),
            }
            update_winner(service, spreadsheet_id, post_id=post_id, topic=row.get("Topic", ""), metrics=metric_map, baseline=baseline)

    post_rows = get_bank_rows(service, spreadsheet_id)
    winner_rows = _rows(service, spreadsheet_id, "ContentWinners", SYSTEM_SHEETS["ContentWinners"])
    authority = build_authority_rows(post_rows, winner_rows)
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="AuthorityMap!A1:G1", valueInputOption="RAW",
        body={"values": [SYSTEM_SHEETS["AuthorityMap"]]},
    ).execute()
    if authority:
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id, range="AuthorityMap!A:G", valueInputOption="RAW",
            insertDataOption="INSERT_ROWS", body={"values": authority},
        ).execute()
    print(json.dumps({"metrics": len(metrics), "winners_scored": len(metrics), "authority_rows": len(authority)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
