from __future__ import annotations

import json
import os
from pathlib import Path

from blogger_publisher import BloggerPublishError, publish_article, upload_blogger_image
from config import load_blogger_config
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row, HEADERS

BLOGGER_ARTIFACT_DIR = "generated/blogger"

def repair_published_image(svc, bid: str, row: dict[str, str]) -> bool:
    post_id = str(row.get("Blogger Post ID", "")).strip()
    source_id = str(row.get("ID", "")).strip()
    image_path = Path("generated") / f"{source_id}.jpg" if source_id else Path("")
    old_url = str(row.get("رابط الصورة", "")).strip()
    if not post_id or not image_path.is_file() or not old_url:
        return False
    try:
        current = svc.posts().get(blogId=bid, postId=post_id).execute()
        content = str(current.get("content", "") or "")
        if old_url not in content:
            return False
        hosted = upload_blogger_image(str(image_path))
        repaired = content.replace(old_url, hosted, 1)
        svc.posts().patch(blogId=bid, postId=post_id, body={"content": repaired}).execute()
        print(f"Blogger image repaired for post {post_id}: {hosted}")
        return True
    except Exception as exc:
        print(f"Blogger image repair unavailable for {post_id}: {exc}")
        return False

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
    bid = blog_id(service, config["blog_url"])
    for existing in rows:
        if str(existing.get("Blogger Status", "")).strip().upper() == "PUBLISHED":
            repair_published_image(service, bid, existing)
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

    # Prefer the item that was just published by the social production run.
    # This keeps Blogger on the exact same scheduled content slot instead of
    # accidentally taking an older unpublished row.
    def _recent_key(item):
        _, r = item
        raw = str(r.get("وقت آخر تشغيل", "") or "").strip()
        try:
            from datetime import datetime
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    candidates.sort(key=_recent_key, reverse=True)
    row_number, row = candidates[0]
    topic = str(row.get("الموضوع", "")).strip()
    post = str(row.get("المحتوى", "")).strip()
    image_url = str(row.get("رابط الصورة", "")).strip()
    source_id = str(row.get("ID", "")).strip()
    image_path = str(Path("generated") / f"{source_id}.jpg") if source_id else ""
    if not Path(image_path).is_file():
        image_path = ""
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
            image_path=image_path,
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
