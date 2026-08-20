from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from .sheets import get_values
except ImportError:
    from sheets import get_values


BANK_SHEET = "PostBank"
BANK_HEADERS = [
    "Bank ID",
    "الموضوع",
    "المحتوى",
    "تاريخ النشر",
    "المنصة",
    "Facebook Post ID",
    "LinkedIn Post ID",
    "رابط الصورة",
    "المصادر القانونية",
    "زاوية المحتوى",
    "هدف المحتوى",
    "المراجعة القانونية",
    "وقت الإضافة",
    "Source Row ID",
]


def ensure_post_bank_sheet(service, spreadsheet_id: str) -> None:
    metadata = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties",
    ).execute()
    existing = {
        str(sheet.get("properties", {}).get("title", "")).strip().casefold()
        for sheet in metadata.get("sheets", [])
    }

    if BANK_SHEET.casefold() not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": BANK_SHEET}}}]},
        ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{BANK_SHEET}!A1:N1",
        valueInputOption="RAW",
        body={"values": [BANK_HEADERS]},
    ).execute()


def add_published_post(
    service,
    spreadsheet_id: str,
    *,
    source_row_id: str,
    topic: str,
    content: str,
    publish_date: str,
    facebook_post_id: str = "",
    linkedin_post_id: str = "",
    image_url: str = "",
    legal_sources: str = "",
    angle: str = "",
    objective: str = "",
    review_level: str = "CLEAR",
) -> None:
    ensure_post_bank_sheet(service, spreadsheet_id)
    row = [
        source_row_id or "",
        topic or "",
        content or "",
        publish_date or "",
        "Facebook + LinkedIn",
        facebook_post_id or "",
        linkedin_post_id or "",
        image_url or "",
        legal_sources or "",
        angle or "",
        objective or "",
        review_level or "",
        datetime.now().astimezone().isoformat(),
        source_row_id or "",
    ]
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{BANK_SHEET}!A:N",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


def get_bank_rows(service, spreadsheet_id: str) -> list[dict[str, str]]:
    ensure_post_bank_sheet(service, spreadsheet_id)
    values = get_values(service, spreadsheet_id, f"{BANK_SHEET}!A:N")
    if len(values) <= 1:
        return []
    rows: list[dict[str, str]] = []
    for raw in values[1:]:
        padded = list(raw) + [""] * (len(BANK_HEADERS) - len(raw))
        rows.append({BANK_HEADERS[i]: str(padded[i]) for i in range(len(BANK_HEADERS))})
    return rows


def build_previous_context(rows: list[dict[str, str]], limit: int = 12) -> str:
    selected = rows[-limit:]
    return "\n".join(
        f"- {row.get('الموضوع','')}: {row.get('زاوية المحتوى','')}"
        for row in selected
        if row.get("الموضوع", "").strip()
    )
