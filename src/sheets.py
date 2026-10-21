from __future__ import annotations

import socket
import time
from typing import Any, Callable, TypeVar

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "ID", "الموضوع", "تاريخ النشر", "ساعة النشر", "نوع الجدولة", "الحالة",
    "المحتوى", "وصف الصورة", "رابط الصورة", "Facebook Status", "LinkedIn Status",
    "Facebook Post ID", "LinkedIn Post ID", "Facebook Comment Status", "Facebook Comment ID",
    "Facebook Like Status", "LinkedIn Image ID", "آخر خطأ", "وقت آخر تشغيل",
    "المصادر القانونية", "ملاحظات", "Image QA Status", "Image QA Score", "Image QA Issues", "Image QA Attempt", "Image Mode",
    "Facebook Comment Queue", "Facebook Comments Published", "Facebook Reaction Status",
    "LinkedIn Comment Queue", "LinkedIn Comments Published", "LinkedIn Reaction Status",
    "Blogger Status", "Blogger Post ID", "Blogger URL", "Blogger Search Title", "Blogger Search Query",
    "Blogger Search Candidates", "Blogger Meta Description", "Blogger SEO Status", "Blogger SEO Error", "Blogger SEO Verified At", "Blogger Last Error",
    "Reel Status", "Reel Script", "Reel File", "Reel Run ID", "Reel Approval",
    "Reel Review", "Reel Facebook ID", "Reel LinkedIn ID", "Reel Last Error",
    "Reel Published At", "Reel QA Score", "Reel QA Issues",
    "Reel YouTube ID", "Reel YouTube URL",
]

SHEET_LAST_COLUMN = "BE"

T = TypeVar("T")

# Google Sheets can occasionally return transient 429/5xx responses or network
# read timeouts. Retry only those temporary failures; authentication, permission,
# and other request errors are allowed to fail immediately so real configuration
# problems remain visible.
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 2.0
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def _execute_with_retry(request_factory: Callable[[], Any], operation: str) -> Any:
    """Execute a Google API request with bounded exponential backoff for transient errors."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return request_factory().execute()
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status not in TRANSIENT_STATUS_CODES or attempt >= MAX_RETRIES:
                raise

            delay = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(
                f"Google Sheets temporary error ({status}) during {operation}; "
                f"retry {attempt}/{MAX_RETRIES - 1} in {delay:.0f}s..."
            )
            time.sleep(delay)
        except (TimeoutError, socket.timeout) as exc:
            if attempt >= MAX_RETRIES:
                print(
                    f"Google Sheets network timeout during {operation}; "
                    f"retries exhausted after {MAX_RETRIES} attempts."
                )
                raise

            delay = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(
                f"Google Sheets network timeout during {operation}; "
                f"retry {attempt}/{MAX_RETRIES - 1} in {delay:.0f}s..."
            )
            time.sleep(delay)

    raise RuntimeError(f"Google API request failed unexpectedly during {operation}.")


def create_service(service_account_info: dict):
    creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def get_values(service, spreadsheet_id: str, sheet_range: str) -> list[list[str]]:
    response = _execute_with_retry(
        lambda: service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=sheet_range,
            majorDimension="ROWS",
        ),
        f"reading {sheet_range}",
    )
    return response.get("values", [])


def row_to_dict(row: list[str], headers: list[str] | None = None) -> dict[str, str]:
    """Map a sheet row using its live header row; fall back only when unavailable."""
    active_headers = [str(value or "").strip() for value in headers] if headers and any(str(value or "").strip() for value in headers) else HEADERS
    padded = list(row) + [""] * max(0, len(active_headers) - len(row))
    return {header: str(padded[i] or "") for i, header in enumerate(active_headers) if header}


def ensure_headers(service, spreadsheet_id: str, sheet_name: str = "Content") -> None:
    existing = get_values(service, spreadsheet_id, f"{sheet_name}!A1:{SHEET_LAST_COLUMN}1")
    if existing and existing[0][:len(HEADERS)] == HEADERS:
        return
    _execute_with_retry(
        lambda: service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1:{SHEET_LAST_COLUMN}1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ),
        f"updating headers in {sheet_name}",
    )


def update_row(service, spreadsheet_id: str, sheet_name: str, row_number: int, values: dict[str, Any]) -> None:
    """Update named cells using the sheet's actual header positions, preserving unrelated columns."""
    header_values = get_values(service, spreadsheet_id, f"{sheet_name}!A1:{SHEET_LAST_COLUMN}1")
    headers = [str(value or "").strip() for value in header_values[0]] if header_values else []
    if not headers or not any(headers):
        headers = HEADERS
    current = get_values(service, spreadsheet_id, f"{sheet_name}!A{row_number}:{SHEET_LAST_COLUMN}{row_number}")
    row = list(current[0]) if current else []
    row += [""] * max(0, len(headers) - len(row))
    for key, value in values.items():
        if key in headers:
            row[headers.index(key)] = "" if value is None else str(value)
    width = max(len(headers), len(row))
    row += [""] * max(0, width - len(row))
    last_column = _column_letter(width)
    _execute_with_retry(
        lambda: service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A{row_number}:{last_column}{row_number}",
            valueInputOption="RAW",
            body={"values": [row]},
        ),
        f"updating row {row_number} in {sheet_name}",
    )


def append_row(service, spreadsheet_id: str, sheet_name: str, values: dict[str, Any]) -> int:
    row = [values.get(header, "") for header in HEADERS]
    response = _execute_with_retry(
        lambda: service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A:{SHEET_LAST_COLUMN}",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ),
        f"appending row to {sheet_name}",
    )
    updated_range = response.get("updates", {}).get("updatedRange", "")
    digits = "".join(ch for ch in updated_range if ch.isdigit())
    return int(digits) if digits else -1



def _column_letter(column_number: int) -> str:
    """Convert a 1-based column number to an A1 column label."""
    label = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        label = chr(65 + remainder) + label
    return label


def _ensure_sheet(service, spreadsheet_id: str, sheet_name: str, headers: list[str]) -> None:
    """Create a generic analysis tab when missing and ensure its header row."""
    sheet_id, resolved_title = _find_sheet_id(service, spreadsheet_id, sheet_name)

    if sheet_id is None:
        _execute_with_retry(
            lambda: service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
            ),
            f"creating sheet tab '{sheet_name}'",
        )
        resolved_title = sheet_name

    last_column = _column_letter(max(1, len(headers)))
    existing = get_values(
        service,
        spreadsheet_id,
        f"{resolved_title}!A1:{last_column}1",
    )
    if existing and existing[0][:len(headers)] == headers:
        return

    _execute_with_retry(
        lambda: service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{resolved_title}!A1:{last_column}1",
            valueInputOption="RAW",
            body={"values": [headers]},
        ),
        f"writing headers in {resolved_title}",
    )


def _append(service, spreadsheet_id: str, sheet_name: str, values: list[Any]) -> int:
    """Append a generic positional row to an analysis tab."""
    last_column = _column_letter(max(1, len(values)))
    response = _execute_with_retry(
        lambda: service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A:{last_column}",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [values]},
        ),
        f"appending row to {sheet_name}",
    )
    updated_range = response.get("updates", {}).get("updatedRange", "")
    digits = "".join(ch for ch in updated_range if ch.isdigit())
    return int(digits) if digits else -1

def _find_sheet_id(service, spreadsheet_id: str, sheet_name: str):
    metadata = _execute_with_retry(
        lambda: service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets.properties",
        ),
        f"resolving sheet tab '{sheet_name}'",
    )
    wanted = sheet_name.strip().casefold()
    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties", {})
        title = str(properties.get("title", "")).strip()
        if title.casefold() == wanted:
            return properties.get("sheetId"), title
    return None, None


def insert_row_at_top(service, spreadsheet_id: str, sheet_name: str, values: dict[str, Any]) -> int:
    """Insert a row below the header; fall back to append if metadata cannot resolve the tab."""
    sheet_id, resolved_title = _find_sheet_id(service, spreadsheet_id, sheet_name)

    if sheet_id is None:
        print(f"Google Sheets metadata did not resolve tab '{sheet_name}'. Falling back to append().")
        return append_row(service, spreadsheet_id, sheet_name, values)

    _execute_with_retry(
        lambda: service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [{
                    "insertDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": 1,
                            "endIndex": 2,
                        },
                        "inheritFromBefore": False,
                    }
                }]
            },
        ),
        f"inserting row below header in {resolved_title}",
    )

    row = [values.get(header, "") for header in HEADERS]
    _execute_with_retry(
        lambda: service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{resolved_title}!A2:{SHEET_LAST_COLUMN}2",
            valueInputOption="RAW",
            body={"values": [row]},
        ),
        f"writing inserted row in {resolved_title}",
    )
    return 2
