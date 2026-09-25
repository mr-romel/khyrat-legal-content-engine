from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from comment_engine import generate_comments
from config import load_facebook_engagement_config
from engagement_strategy import choose_comment_count, normalize_comment
from facebook_publisher import add_comment, like_comment, like_post
from sheets import create_service, get_values

ENGAGEMENT_SHEET = os.getenv("FACEBOOK_ENGAGEMENT_SHEET", "Facebook Engagement").strip() or "Facebook Engagement"
HEADERS = [
    "event_id", "source_row", "post_id", "topic", "post_text", "legal_sources",
    "action", "sequence", "scheduled_at", "status", "comment_text", "comment_id",
    "attempts", "last_error", "fingerprint", "created_at", "updated_at", "dry_run",
]
CAIRO = ZoneInfo("Africa/Cairo")
MAX_ATTEMPTS = int(os.getenv("FACEBOOK_ENGAGEMENT_MAX_ATTEMPTS", "3") or "3")
RETRY_MINUTES = int(os.getenv("FACEBOOK_ENGAGEMENT_RETRY_MINUTES", "30") or "30")
MAX_COMMENTS_PER_RUN = 1


def now_cairo():
    return datetime.now(CAIRO)


def iso(dt):
    return dt.astimezone(CAIRO).isoformat()


def parse_dt(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CAIRO)
    return dt.astimezone(CAIRO)


def fingerprint(post_id: str, message: str) -> str:
    return hashlib.sha256(f"{post_id}|{message}".encode("utf-8")).hexdigest()[:24]


def col_letter(n):
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def ensure_sheet(service, spreadsheet_id):
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
    exists = any(
        str(x.get("properties", {}).get("title", "")).strip().casefold() == ENGAGEMENT_SHEET.casefold()
        for x in meta.get("sheets", [])
    )
    if not exists:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": ENGAGEMENT_SHEET}}}]},
        ).execute()
    last = col_letter(len(HEADERS))
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{ENGAGEMENT_SHEET}!A1:{last}1",
        valueInputOption="RAW",
        body={"values": [HEADERS]},
    ).execute()


def read_events(service, spreadsheet_id):
    last = col_letter(len(HEADERS))
    values = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{ENGAGEMENT_SHEET}!A1:{last}",
    ).execute().get("values", [])
    result = []
    for row_number, raw in enumerate(values[1:], start=2):
        padded = list(raw) + [""] * (len(HEADERS) - len(raw))
        item = {HEADERS[i]: str(padded[i]) for i in range(len(HEADERS))}
        item["_row_number"] = str(row_number)
        result.append(item)
    return result


def append_event(service, spreadsheet_id, event):
    last = col_letter(len(HEADERS))
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{ENGAGEMENT_SHEET}!A:{last}",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [[event.get(h, "") for h in HEADERS]]},
    ).execute()


def update_event(service, spreadsheet_id, row_number, changes):
    last = col_letter(len(HEADERS))
    current = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{ENGAGEMENT_SHEET}!A{row_number}:{last}{row_number}",
    ).execute().get("values", [[]])
    row = list(current[0]) if current else []
    row += [""] * (len(HEADERS) - len(row))
    for key, value in changes.items():
        if key in HEADERS:
            row[HEADERS.index(key)] = str(value)
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{ENGAGEMENT_SHEET}!A{row_number}:{last}{row_number}",
        valueInputOption="RAW",
        body={"values": [row[:len(HEADERS)]]},
    ).execute()


def _published_at(row, current):
    date_text = str(row.get("تاريخ النشر", "")).strip()
    time_text = str(row.get("ساعة النشر", "")).strip()
    dm = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_text)
    tm = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", time_text)
    if dm and tm:
        try:
            return datetime(
                int(dm.group(1)), int(dm.group(2)), int(dm.group(3)),
                int(tm.group(1)), int(tm.group(2)), int(tm.group(3) or 0),
                tzinfo=CAIRO,
            )
        except ValueError:
            pass
    return current


def read_content(service, spreadsheet_id, sheet_range):
    values = get_values(service, spreadsheet_id, sheet_range)
    headers = list(values[0]) if values else []
    result = []
    for row_number, raw in enumerate(values[1:], start=2):
        padded = list(raw) + [""] * (len(headers) - len(raw))
        result.append((row_number, {str(headers[i]): str(padded[i]) for i in range(len(headers))}))
    return result


def enqueue_latest_post(service, spreadsheet_id, sheet_range, events, current, dry_run):
    bundled = {
        str(x.get("post_id", "")).strip()
        for x in events
        if str(x.get("event_id", "")).startswith("COMMENT_BUNDLE:")
    }
    candidates = []
    for source_row, row in read_content(service, spreadsheet_id, sheet_range):
        post_id = str(row.get("Facebook Post ID", "")).strip()
        status = str(row.get("Facebook Status", "")).strip().upper()
        if status != "PUBLISHED" or not post_id:
            continue
        candidates.append((_published_at(row, current), source_row, row, post_id))
    if not candidates:
        return 0
    candidates.sort(key=lambda x: (x[0], int(x[1])), reverse=True)
    published_at, source_row, row, post_id = candidates[0]
    if post_id in bundled:
        return 0

    target_count = choose_comment_count(f"{row.get('الموضوع', '')}|{row.get('المحتوى', '')}")
    published_comment_count = sum(
        1
        for event in events
        if str(event.get("post_id", "")).strip() == post_id
        and str(event.get("action", "")).upper() == "COMMENT"
        and str(event.get("status", "")).upper() == "PUBLISHED"
    )
    if published_comment_count >= target_count:
        print(
            f"Facebook comment target already reached for {post_id}: "
            f"{published_comment_count}/{target_count}; no new comments queued."
        )
        return 0

    count = target_count - published_comment_count
    generated = generate_comments(
        api_key=CONFIG["gemini_api_key"],
        model=CONFIG["gemini_model"],
        topic=row.get("الموضوع", ""),
        post=row.get("المحتوى", ""),
        legal_sources=row.get("المصادر القانونية", ""),
        count=count,
    )
    comments = generated.get("facebook_comments", [])
    if len(comments) != count:
        raise RuntimeError(f"Facebook comment generation returned {len(comments)}; expected {count}")

    bundle_id = f"COMMENT_BUNDLE:{post_id}"
    append_event(service, spreadsheet_id, {
        "event_id": f"{bundle_id}:REACTION",
        "source_row": str(source_row),
        "post_id": post_id,
        "topic": row.get("الموضوع", ""),
        "post_text": row.get("المحتوى", ""),
        "legal_sources": row.get("المصادر القانونية", ""),
        "action": "REACTION",
        "sequence": "0",
        "scheduled_at": iso(published_at),
        "status": "PENDING",
        "comment_text": "",
        "attempts": "0",
        "fingerprint": fingerprint(post_id, "__LIKE_POST__"),
        "created_at": iso(current),
        "updated_at": iso(current),
        "dry_run": "true" if dry_run else "false",
    })

    # If discovery happens late, do not create an already-overdue backlog.
    # Comment 1 is due now; later comments are spaced from this worker's
    # discovery time and subsequently re-based from each real publication.
    bundle_anchor = current
    for sequence, message in enumerate(comments, start=1):
        clean = normalize_comment(message)
        scheduled = bundle_anchor + timedelta(minutes=15 * (sequence - 1))
        append_event(service, spreadsheet_id, {
            "event_id": f"{bundle_id}:{sequence}",
            "source_row": str(source_row),
            "post_id": post_id,
            "topic": row.get("الموضوع", ""),
            "post_text": row.get("المحتوى", ""),
            "legal_sources": row.get("المصادر القانونية", ""),
            "action": "COMMENT",
            "sequence": str(sequence),
            "scheduled_at": iso(scheduled),
            "status": "PENDING",
            "comment_text": clean,
            "attempts": "0",
            "fingerprint": fingerprint(post_id, clean),
            "created_at": iso(current),
            "updated_at": iso(current),
            "dry_run": "true" if dry_run else "false",
        })
    print(f"Queued {count} Facebook comments for {post_id}")
    return count


def _latest_bundle_post(events):
    bundles = []
    for event in events:
        event_id = str(event.get("event_id", "")).strip()
        if not event_id.startswith("COMMENT_BUNDLE:"):
            continue
        post_id = str(event.get("post_id", "")).strip()
        if not post_id:
            continue
        created = parse_dt(event.get("created_at", "")) or datetime.min.replace(tzinfo=CAIRO)
        source_row = int(event.get("source_row", "0") or "0")
        bundles.append((created, source_row, post_id))
    if not bundles:
        return ""
    bundles.sort(reverse=True)
    return bundles[0][2]


def _rebaseline_pending_comments(service, spreadsheet_id, events, post_id, anchor, interval_minutes=15):
    """Keep the remaining bundle on a real 15-minute clock after a delayed run."""
    pending = [
        x for x in events
        if str(x.get("post_id", "")).strip() == post_id
        and str(x.get("action", "")).upper() == "COMMENT"
        and str(x.get("status", "")).upper() in {"PENDING", "RETRY"}
    ]
    pending.sort(key=lambda x: int(x.get("sequence", "0") or "0"))
    for index, event in enumerate(pending, start=1):
        target = anchor + timedelta(minutes=interval_minutes * index)
        current_scheduled = parse_dt(event.get("scheduled_at", ""))
        if current_scheduled is None or abs((current_scheduled - target).total_seconds()) > 1:
            update_event(
                service,
                spreadsheet_id,
                int(event["_row_number"]),
                {"scheduled_at": iso(target), "updated_at": iso(anchor)},
            )


def due_events(events, current):
    latest_post = _latest_bundle_post(events)
    due = []
    for event in events:
        if str(event.get("post_id", "")).strip() != latest_post:
            continue
        if str(event.get("status", "")).upper() not in {"PENDING", "RETRY"}:
            continue
        scheduled = parse_dt(event.get("scheduled_at", ""))
        if not scheduled or scheduled > current:
            continue
        if str(event.get("action", "")).upper() not in {"COMMENT", "REACTION"}:
            continue
        due.append(event)
    due.sort(key=lambda x: (parse_dt(x.get("scheduled_at", "")) or current, int(x.get("_row_number", "0"))))
    # Exactly one new comment per worker cycle. The next comment is re-based
    # from the actual successful publication time, so a missed cron run cannot
    # create an hours/days catch-up backlog.
    return due[:MAX_COMMENTS_PER_RUN]


def main():
    global CONFIG
    CONFIG = load_facebook_engagement_config()
    dry_run = os.getenv("KHYRAT_FACEBOOK_ENGAGEMENT_DRY_RUN", "false").strip().lower() in {"1", "true", "yes", "on"}
    service = create_service(CONFIG["service_account_info"])
    ensure_sheet(service, CONFIG["sheet_id"])
    current = now_cairo()
    events = read_events(service, CONFIG["sheet_id"])

    enqueue_latest_post(service, CONFIG["sheet_id"], CONFIG["sheet_range"], events, current, dry_run)
    events = read_events(service, CONFIG["sheet_id"])
    due = due_events(events, current)
    print(f"Facebook due events: {len(due)}")
    if not due:
        return 0

    for event in due:
        row_number = int(event["_row_number"])
        attempts = int(event.get("attempts", "0") or "0") + 1
        if dry_run:
            update_event(service, CONFIG["sheet_id"], row_number, {
                "status": "DRY_RUN_READY",
                "attempts": attempts,
                "last_error": "DRY RUN: no Facebook engagement was sent",
                "updated_at": iso(current),
            })
            continue

        if str(event.get("action", "")).upper() == "REACTION":
            result = like_post(
                post_id=event["post_id"],
                page_access_token=CONFIG["facebook_page_access_token"],
                graph_version=CONFIG["facebook_graph_version"],
            )
        else:
            result = add_comment(
            post_id=event["post_id"],
            page_access_token=CONFIG["facebook_page_access_token"],
            graph_version=CONFIG["facebook_graph_version"],
            message=event["comment_text"],
        )
        changes = {
            "attempts": attempts,
            "last_error": result.get("error", ""),
            "updated_at": iso(current),
        }
        if result.get("status") in {"PUBLISHED", "LIKED"}:
            comment_id = result.get("comment_id", "")
            changes.update({
                "status": result.get("status"),
                "comment_id": comment_id,
                "last_error": "",
            })
            print(f"{event['event_id']} -> PUBLISHED")
        elif attempts >= MAX_ATTEMPTS:
            changes["status"] = "FAILED"
            print(f"{event['event_id']} -> FAILED")
        else:
            changes.update({
                "status": "RETRY",
                "scheduled_at": iso(current + timedelta(minutes=RETRY_MINUTES)),
            })
            print(f"{event['event_id']} -> RETRY")
        update_event(service, CONFIG["sheet_id"], row_number, changes)

        if str(event.get("action", "")).upper() == "COMMENT" and result.get("status") == "PUBLISHED":
            refreshed = read_events(service, CONFIG["sheet_id"])
            _rebaseline_pending_comments(
                service,
                CONFIG["sheet_id"],
                refreshed,
                event["post_id"],
                current,
                interval_minutes=15,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
