from __future__ import annotations

from datetime import datetime


SHEET = "Analytics"
HEADERS = [
    "Date",
    "Source Row ID",
    "Topic",
    "Pillar",
    "Objective",
    "Facebook Post ID",
    "LinkedIn Post ID",
    "Facebook Comments Created",
    "LinkedIn Comments Created",
    "Status",
]


def ensure_sheet(service, spreadsheet_id: str) -> None:
    metadata = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties",
    ).execute()
    titles = {
        str(s.get("properties", {}).get("title", "")).strip().casefold()
        for s in metadata.get("sheets", [])
    }
    if SHEET.casefold() not in titles:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": SHEET}}}]},
        ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET}!A1:J1",
        valueInputOption="RAW",
        body={"values": [HEADERS]},
    ).execute()


def _source_row_already_logged(service, spreadsheet_id: str, source_row_id: str) -> bool:
    source = str(source_row_id or "").strip()
    if not source:
        return False
    values = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET}!B2:B",
        majorDimension="ROWS",
    ).execute().get("values", [])
    return any(str(row[0]).strip() == source for row in values if row)


def log_publication(service, spreadsheet_id: str, **data: str) -> bool:
    """Log a publication once only; retries must not create duplicate analytics rows."""
    ensure_sheet(service, spreadsheet_id)
    source_row_id = str(data.get("source_row_id", "") or "").strip()
    if _source_row_already_logged(service, spreadsheet_id, source_row_id):
        print(f"Analytics idempotency: source row {source_row_id} is already logged; skipping duplicate entry.")
        return False

    row = [
        data.get("date", datetime.now().astimezone().isoformat()),
        source_row_id,
        data.get("topic", ""),
        data.get("pillar", ""),
        data.get("objective", ""),
        data.get("facebook_post_id", ""),
        data.get("linkedin_post_id", ""),
        data.get("facebook_comments", "0"),
        data.get("linkedin_comments", "0"),
        data.get("status", "PUBLISHED"),
    ]
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET}!A:J",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
    return True
