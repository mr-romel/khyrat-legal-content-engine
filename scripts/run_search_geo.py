from __future__ import annotations

import os

from config import _service_account_info, _required, _optional
from sheets import create_service, get_values, row_to_dict
from search_geo import record_search_geo, SEARCH_GEO_HEADERS


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

    for raw in rows[1:]:
        row = row_to_dict(raw)
        post_id = str(row.get("ID", "")).strip()
        if not post_id or post_id in existing_ids:
            continue

        topic = str(row.get("الموضوع", "")).strip()
        post = str(row.get("المحتوى", "")).strip()
        if not topic and not post:
            continue

        platform = "FACEBOOK+LINKEDIN"
        record_search_geo(
            service,
            spreadsheet_id,
            post_id=post_id,
            topic=topic,
            post=post,
            platform=platform,
            legal_sources=str(row.get("المصادر القانونية", "")).strip(),
        )
        existing_ids.add(post_id)
        created += 1

    print(f"Search GEO backfill complete: created={created}, existing={len(existing_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
