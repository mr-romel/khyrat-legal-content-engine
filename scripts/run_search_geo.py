from __future__ import annotations

import os

from config import _service_account_info, _required, _optional
from sheets import create_service, get_values, row_to_dict, _execute_with_retry
from search_geo import build_metadata, SEARCH_GEO_HEADERS
from content_system import _ensure_sheet


def main() -> int:
    service = create_service(_service_account_info())
    spreadsheet_id = _required("GOOGLE_SHEET_ID")
    content_range = _optional("GOOGLE_SHEET_RANGE", "Content!A:AF")

    rows = get_values(service, spreadsheet_id, content_range)
    if not rows:
        print("Search GEO: Content sheet is empty.")
        return 0

    existing = get_values(service, spreadsheet_id, "SearchGEO!A:A")
    existing_ids = {str(row[0]).strip() for row in existing[1:] if row}
    created = 0
    pending = []

    for raw in rows[1:]:
        row = row_to_dict(raw)
        post_id = str(row.get("ID", "")).strip()
        if not post_id or post_id in existing_ids:
            continue

        topic = str(row.get("الموضوع", "")).strip()
        post = str(row.get("المحتوى", "")).strip()
        if not topic and not post:
            continue

        data = build_metadata(
            post_id=post_id,
            topic=topic,
            post=post,
            platform="FACEBOOK+LINKEDIN",
            legal_sources=str(row.get("المصادر القانونية", "")).strip(),
        )
        pending.append([data[h] for h in SEARCH_GEO_HEADERS])
        existing_ids.add(post_id)

    _ensure_sheet(service, spreadsheet_id, "SearchGEO", SEARCH_GEO_HEADERS)
    if pending:
        _execute_with_retry(
            lambda: service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range="SearchGEO!A:R",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": pending},
            ),
            "backfilling SearchGEO",
        )
        created = len(pending)

