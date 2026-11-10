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
REQUIRED_HEADERS = (
    "Reel YouTube ID",
    "Reel YouTube Comments Status",
    "Reel YouTube Comment IDs",
    "Blogger URL",
    "الموضوع",
)


def _text(row: dict, *keys: str) -> str:
    for key in keys:
        value = str(row.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _column_letter(column_number: int) -> str:
    label = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        label = chr(65 + remainder) + label
    return label


def _ensure_tracking_headers(service, spreadsheet_id: str, sheet_name: str, headers: list[str]) -> list[str]:
    missing = [name for name in REQUIRED_HEADERS if name not in headers]
    if not missing:
        return headers
    headers = list(headers)
    headers.extend(missing)
    last_column = _column_letter(len(headers))
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A1:{last_column}1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()
    print("YouTube comments: added missing tracking headers at the end of the existing header row: " + ", ".join(missing))
    return headers


def _validate_oauth_environment() -> None:
    missing = [
        name for name in (
            "YOUTUBE_COMMENT_CLIENT_ID",
            "YOUTUBE_COMMENT_CLIENT_SECRET",
            "YOUTUBE_COMMENT_REFRESH_TOKEN",
        )
        if not os.getenv(name, "").strip()
    ]
    if missing:
        raise RuntimeError(
            "YouTube comments OAuth configuration is incomplete. Missing GitHub Actions secret(s): "
            + ", ".join(missing)
            + ". The Client ID and Client Secret must belong to the same Google OAuth client that issued "
              "YOUTUBE_COMMENT_REFRESH_TOKEN; do not substitute the upload OAuth client unless it is the same client."
        )


def run() -> int:
    _validate_oauth_environment()
    config = load_video_config()
    service = create_service(config["service_account_info"])
    configured_range = str(config.get("sheet_range") or "Content!A:BZ")
    sheet_name = configured_range.split("!", 1)[0] if "!" in configured_range else "Content"
    values = get_values(service, config["sheet_id"], f"{sheet_name}!A:BZ")
    if not values:
        print("YouTube comments: content sheet is empty; nothing to process.")
        return 0

    headers = [str(x or "").strip() for x in values[0]]
    headers = _ensure_tracking_headers(service, config["sheet_id"], sheet_name, headers)
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
        candidates.append((row_number, video_id, bundle, published_ids))

    candidates.sort(key=lambda item: item[0], reverse=True)
    for row_number, video_id, bundle, published_ids in candidates:
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
            sheet_name,
            row_number,
            {
                "Reel YouTube Comment IDs": json.dumps(published_ids, ensure_ascii=False),
                "Reel YouTube Comments Status": "PUBLISHED" if complete else "IN_PROGRESS",
            },
        )
        print(
            f"YouTube comments: comment {next_index + 1}/{len(bundle)} published "
            f"for Short {video_id}; id={comment_id}; "
            f"status={'PUBLISHED' if complete else 'IN_PROGRESS'}; {now}"
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
