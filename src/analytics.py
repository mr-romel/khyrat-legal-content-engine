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
    "Similarity Score",
    "Rewrite Applied",
    "Angle",
    "Legal Sources",
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
        range=f"{SHEET}!A1:N1",
        valueInputOption="RAW",
        body={"values": [HEADERS]},
    ).execute()


def log_publication(service, spreadsheet_id: str, **data: str) -> None:
    try:
        ensure_sheet(service, spreadsheet_id)
        row = [
            data.get("date", datetime.now().astimezone().isoformat()),
            data.get("source_row_id", ""),
            data.get("topic", ""),
            data.get("pillar", ""),
            data.get("objective", ""),
            data.get("facebook_post_id", ""),
            data.get("linkedin_post_id", ""),
            data.get("facebook_comments", "0"),
            data.get("linkedin_comments", "0"),
            data.get("status", "PUBLISHED"),
            data.get("similarity_score", ""),
            data.get("rewrite_applied", "NO"),
            data.get("angle", ""),
            data.get("legal_sources", ""),
        ]
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{SHEET}!A:N",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
    except Exception as exc:
        print(f"Analytics logging failed (non-blocking): {exc}")
