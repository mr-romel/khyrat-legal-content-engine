from __future__ import annotations

from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "ID",
    "الموضوع",
    "تاريخ النشر",
    "ساعة النشر",
    "نوع الجدولة",
    "الحالة",
    "المحتوى",
    "وصف الصورة",
    "رابط الصورة",
    "Facebook Status",
    "LinkedIn Status",
    "Facebook Post ID",
    "LinkedIn Post ID",
    "Facebook Comment Status",
    "Facebook Comment ID",
    "Facebook Like Status",
    "LinkedIn Image ID",
    "آخر خطأ",
    "وقت آخر تشغيل",
    "المصادر القانونية",
    "ملاحظات",
]

SHEET_LAST_COLUMN = "U"


def create_service(service_account_info: dict):
    creds = Credentials.from_service_account_info(
        service_account_info,
        scopes=SCOPES,
    )
    return build(
        "sheets",
        "v4",
        credentials=creds,
        cache_discovery=False,
    )


def get_values(
    service,
    spreadsheet_id: str,
    sheet_range: str,
) -> list[list[str]]:
    response = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=sheet_range,
            majorDimension="ROWS",
        )
        .execute()
    )
    return response.get("values", [])


def row_to_dict(row: list[str]) -> dict[str, str]:
    padded = list(row) + [""] * (len(HEADERS) - len(row))
    return {
        HEADERS[i]: padded[i]
        for i in range(len(HEADERS))
    }


def ensure_headers(
    service,
    spreadsheet_id: str,
    sheet_name: str = "Content",
) -> None:
    existing = get_values(
        service,
        spreadsheet_id,
        f"{sheet_name}!A1:{SHEET_LAST_COLUMN}1",
    )
    if existing and existing[0][: len(HEADERS)] == HEADERS:
        return

    (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1:{SHEET_LAST_COLUMN}1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        )
        .execute()
    )


def update_row(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    row_number: int,
    values: dict[str, Any],
) -> None:
    current = get_values(
        service,
        spreadsheet_id,
        f"{sheet_name}!A{row_number}:{SHEET_LAST_COLUMN}{row_number}",
    )

    row = [[""] * len(HEADERS)]
    if current:
        existing = current[0] + [""] * (len(HEADERS) - len(current[0]))
        row[0] = existing[: len(HEADERS)]

    for key, value in values.items():
        if key not in HEADERS:
            continue
        idx = HEADERS.index(key)
        row[0][idx] = "" if value is None else str(value)

    (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A{row_number}:{SHEET_LAST_COLUMN}{row_number}",
            valueInputOption="RAW",
            body={"values": row},
        )
        .execute()
    )


def append_row(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    values: dict[str, Any],
) -> int:
    row = [values.get(header, "") for header in HEADERS]
    response = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A:{SHEET_LAST_COLUMN}",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        )
        .execute()
    )
    updated_range = (
        response.get("updates", {})
        .get("updatedRange", "")
    )
    digits = "".join(ch for ch in updated_range if ch.isdigit())
    return int(digits) if digits else -1


def insert_row_at_top(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    values: dict[str, Any],
) -> int:
    """Insert one complete content row immediately below the header row."""
    metadata = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets.properties",
        )
        .execute()
    )

    sheet_id = None
    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("title") == sheet_name:
            sheet_id = properties.get("sheetId")
            break

    if sheet_id is None:
        raise RuntimeError(
            f"Google Sheet tab '{sheet_name}' was not found."
        )

    (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "insertDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": 1,
                                "endIndex": 2,
                            },
                            "inheritFromBefore": False,
                        }
                    }
                ]
            },
        )
        .execute()
    )

    row = [values.get(header, "") for header in HEADERS]
    (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A2:{SHEET_LAST_COLUMN}2",
            valueInputOption="RAW",
            body={"values": [row]},
        )
        .execute()
    )

    return 2
