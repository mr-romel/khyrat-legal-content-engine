from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from config import load_video_config
from sheets import create_service, get_values, update_row
from video_comments import build_video_comment_bundle, parse_published_comment_ids
from youtube_publisher import publish_youtube_short_comment

CAIRO = ZoneInfo("Africa/Cairo")
MAX_COMMENTS_PER_RUN = max(1, int(os.getenv("YOUTUBE_COMMENTS_PER_RUN", "1") or "1"))


def _text(row: dict, *keys: str) -> str:
    for key in keys:
        value = str(row.get(key, "") or "").strip()
        if value:
            return value
    return ""


def run() -> int:
    config = load_video_config()
    service = create_service(config["service_account_info"])
    configured_range = str(config.get("sheet_range") or "Content!A:BZ")
    sheet_name = configured_range.split("!", 1)[0] if "!" in configured_range else "Content"
    # YouTube comment tracking columns live near the end of the Content tab;
    # always read through BZ even when the general publisher range is shorter.
    values = get_values(service, config["sheet_id"], f"{sheet_name}!A:BZ")
    if not values:
        print("YouTube comments: content sheet is empty; nothing to process.")
        return 0

    headers = [str(x or "").strip() for x in values[0]]
    required = ("Reel YouTube ID", "Reel YouTube Comments Status", "Reel YouTube Comment IDs", "Blogger URL", "الموضوع")
    missing = [name for name in required if name not in headers]
    if missing:
        raise RuntimeError("Content sheet is missing required columns: " + ", ".join(missing))

    now = datetime.now(CAIRO).isoformat()
    processed = 0
    candidates = []
    for row_number, raw in enumerate(values[1:], start=2):
        padded = list(raw) + [""] * max(0, len(headers) - len(raw))
        row = {headers[i]: str(padded[i] or "") for i in range(len(headers))}
        video_id = _text(row, "Reel YouTube ID")
        if not video_id:
            continue
        if _text(row, "Reel Status").upper() not in {"PUBLISHED", "SUCCESS", "POSTED"}:
            continue
        article_url = _text(row, "Blogger URL")
        if not article_url:
            print(f"YouTube comments: row {row_number} has no matching Blogger URL; skipped.")
            continue
        published_ids = parse_published_comment_ids(row.get("Reel YouTube Comment IDs", ""))
        bundle = build_video_comment_bundle(
            topic=_text(row, "الموضوع", "المحتوى"),
            article_url=article_url,
            video_id=video_id,
            platform="youtube",
        )
        status = _text(row, "Reel YouTube Comments Status").upper()
        if len(published_ids) >= len(bundle) or status == "PUBLISHED":
            continue
        candidates.append((row_number, row, video_id, article_url, bundle, published_ids))

    # Newest source rows first. A single comment per run prevents bursts/spam.
    candidates.sort(key=lambda item: item[0], reverse=True)
    for row_number, row, video_id, article_url, bundle, published_ids in candidates:
        if processed >= MAX_COMMENTS_PER_RUN:
            break
        next_index = len(published_ids)
        message = bundle[next_index]
        print(f"YouTube comments: publishing comment {next_index + 1}/{len(bundle)} for Short {video_id}.")
        result = publish_youtube_short_comment(video_id, message)
        comment_id = str(result.get("comment_id", "")).strip()
        if not comment_id:
            raise RuntimeError("YouTube API did not return a comment ID.")
        published_ids.append(comment_id)
        complete = len(published_ids) >= len(bundle)
        update_row(
            service,
            config["sheet_id"],
            "Content",
            row_number,
            {
                "Reel YouTube Comment IDs": json.dumps(published_ids, ensure_ascii=False),
                "Reel YouTube Comments Status": "PUBLISHED" if complete else "IN_PROGRESS",
            },
        )
        print(
            f"YouTube comments: comment {next_index + 1}/{len(bundle)} published "
            f"for Short {video_id}; id={comment_id}; status={'PUBLISHED' if complete else 'IN_PROGRESS'}; {now}"
        )
        processed += 1

    if not candidates:
        print("YouTube comments: no eligible published Shorts with a matching Blogger article.")
    elif processed == 0:
        print("YouTube comments: eligible Shorts already have a complete comment bundle.")
    return processed


if __name__ == "__main__":
    count = run()
    print(f"YouTube comments worker finished; comments published this run: {count}")
