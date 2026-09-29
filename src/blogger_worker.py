from __future__ import annotations

import json
import os
from pathlib import Path

from blogger_publisher import BloggerPublishError, publish_article
from config import load_blogger_config
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row, HEADERS

BLOGGER_ARTIFACT_DIR = "generated/blogger"

def main() -> int:
    config = load_blogger_config()
    if not config["enabled"]:
        print("Blogger publishing disabled; social pipeline continues.")
        return 0

    service = create_service(config["service_account_info"])
    sheet_name = config["sheet_range"].split("!", 1)[0]
    ensure_headers(service, config["sheet_id"], sheet_name)
    values = get_values(service, config["sheet_id"], config["sheet_range"])
    if not values:
        print("Blogger worker: no sheet rows.")
        return 0

    rows = [row_to_dict(row) for row in values[1:]]
    candidates = []
    for row_number, row in enumerate(rows, start=2):
        if str(row.get("الحالة", "")).strip().upper() != "PUBLISHED":
            continue
        if str(row.get("Blogger Status", "")).strip().upper() == "PUBLISHED":
            continue
        # Blogger is independent from social publication. A valid published
        # content row is enough; Facebook/LinkedIn IDs are not required.
        if not str(row.get("المحتوى", "")).strip():
            continue
        candidates.append((row_number, row))

    if not candidates:
        print("Blogger worker: no unpublished Blogger rows.")
        return 0

    row_number, row = candidates[-1]
    topic = str(row.get("الموضوع", "")).strip()
    post = str(row.get("المحتوى", "")).strip()
    image_url = str(row.get("رابط الصورة", "")).strip()
    legal_sources = str(row.get("المصادر القانونية", "")).strip()

    update_row(service, config["sheet_id"], sheet_name, row_number, {
        "Blogger Status": "PROCESSING",
        "Blogger Last Error": "",
    })

    if os.getenv("BLOGGER_DRY_RUN", "false").strip().lower() in {"1", "true", "yes", "on"}:
        print(f"Blogger DRY RUN: row={row_number}, topic={topic}, title source ready; no post will be published.")
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Blogger Status": "DRY_RUN_READY",
            "Blogger Last Error": "",
        })
        return 0

    try:
        result = publish_article(
            topic=topic,
            post=post,
            image_url=image_url,
            legal_sources=legal_sources,
            output_dir=f"{BLOGGER_ARTIFACT_DIR}/row_{row_number}",
        )
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Blogger Status": "PUBLISHED",
            "Blogger Post ID": result["post_id"],
            "Blogger URL": result["post_url"],
            "Blogger Search Title": result["title"],
            "Blogger Search Query": result["search_query"],
            "Blogger Search Candidates": result["search_candidates"],
            "Blogger Last Error": "",
        })
        print(f"Blogger published: {result['title']} -> {result['post_url']}")
        return 0
    except BloggerPublishError as exc:
        error = str(exc)[:1500]
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Blogger Status": "FAILED",
            "Blogger Last Error": error,
        })
        print(f"Blogger publication failed (retryable): {error}")
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
