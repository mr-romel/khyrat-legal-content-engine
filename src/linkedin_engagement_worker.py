from __future__ import annotations

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import load_engagement_config
from linkedin_comment_engine import choose_comment_count, comment_schedule_offsets, generate_linkedin_comments
from linkedin_engagement import add_linkedin_comment, comment_fingerprint
from linkedin_publisher import resolve_member_urn
from sheets import create_service, get_values

ENGAGEMENT_SHEET = os.getenv("LINKEDIN_ENGAGEMENT_SHEET", "LinkedIn Engagement").strip() or "LinkedIn Engagement"
CONTENT_HEADERS = [
    "ID", "الموضوع", "تاريخ النشر", "ساعة النشر", "نوع الجدولة", "الحالة",
    "المحتوى", "وصف الصورة", "رابط الصورة", "Facebook Status", "LinkedIn Status",
    "Facebook Post ID", "LinkedIn Post ID", "Facebook Comment Status", "Facebook Comment ID",
    "Facebook Like Status", "LinkedIn Image ID", "آخر خطأ", "وقت آخر تشغيل",
    "المصادر القانونية", "ملاحظات",
]
ENGAGEMENT_HEADERS = [
    "event_id", "source_row", "post_urn", "topic", "post_text", "legal_sources",
    "action", "sequence", "scheduled_at", "status", "comment_text", "comment_urn",
    "attempts", "last_http_status", "last_error", "capability_status", "fingerprint",
    "created_at", "updated_at", "dry_run",
]
CAIRO = ZoneInfo("Africa/Cairo")
MAX_ATTEMPTS = int(os.getenv("LINKEDIN_ENGAGEMENT_MAX_ATTEMPTS", "3") or "3")
RETRY_MINUTES = int(os.getenv("LINKEDIN_ENGAGEMENT_RETRY_MINUTES", "30") or "30")
DISCOVERY_HOURS = int(os.getenv("LINKEDIN_ENGAGEMENT_DISCOVERY_HOURS", "48") or "48")
PERMISSION_RECHECK_HOURS = int(os.getenv("LINKEDIN_PERMISSION_RECHECK_HOURS", "24") or "24")
MAX_COMMENTS_PER_POST_PER_RUN = 1


def now_cairo():
    return datetime.now(CAIRO)


def iso(dt):
    return dt.astimezone(CAIRO).isoformat()


def parse_dt(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CAIRO)
    return parsed.astimezone(CAIRO)


def col_letter(n):
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def sheet_exists(service, spreadsheet_id, title):
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
    return any(str(s.get("properties", {}).get("title", "")).strip().casefold() == title.casefold() for s in meta.get("sheets", []))


def ensure_engagement_sheet(service, spreadsheet_id):
    if not sheet_exists(service, spreadsheet_id, ENGAGEMENT_SHEET):
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": ENGAGEMENT_SHEET}}}]},
        ).execute()
    last = col_letter(len(ENGAGEMENT_HEADERS))
    current = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{ENGAGEMENT_SHEET}!A1:{last}1"
    ).execute().get("values", [])
    if not current or current[0][:len(ENGAGEMENT_HEADERS)] != ENGAGEMENT_HEADERS:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"{ENGAGEMENT_SHEET}!A1:{last}1",
            valueInputOption="RAW", body={"values": [ENGAGEMENT_HEADERS]}
        ).execute()


def read_engagement_rows(service, spreadsheet_id):
    last = col_letter(len(ENGAGEMENT_HEADERS))
    values = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{ENGAGEMENT_SHEET}!A1:{last}",
        majorDimension="ROWS"
    ).execute().get("values", [])
    rows = []
    for idx, raw in enumerate(values[1:], start=2):
        padded = list(raw) + [""] * (len(ENGAGEMENT_HEADERS) - len(raw))
        item = {ENGAGEMENT_HEADERS[i]: str(padded[i]) for i in range(len(ENGAGEMENT_HEADERS))}
        item["_row_number"] = str(idx)
        rows.append(item)
    return rows


def append_event(service, spreadsheet_id, event):
    last = col_letter(len(ENGAGEMENT_HEADERS))
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range=f"{ENGAGEMENT_SHEET}!A:{last}",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [[event.get(h, "") for h in ENGAGEMENT_HEADERS]]}
    ).execute()


def update_event(service, spreadsheet_id, row_number, changes):
    last = col_letter(len(ENGAGEMENT_HEADERS))
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{ENGAGEMENT_SHEET}!A{row_number}:{last}{row_number}"
    ).execute().get("values", [])
    row = list(response[0]) if response else []
    row += [""] * (len(ENGAGEMENT_HEADERS) - len(row))
    for key, value in changes.items():
        if key in ENGAGEMENT_HEADERS:
            row[ENGAGEMENT_HEADERS.index(key)] = str(value)
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"{ENGAGEMENT_SHEET}!A{row_number}:{last}{row_number}",
        valueInputOption="RAW", body={"values": [row[:len(ENGAGEMENT_HEADERS)]]}
    ).execute()


def read_content_rows(service, spreadsheet_id, sheet_range):
    values = get_values(service, spreadsheet_id, sheet_range)
    result = []
    for row_number, raw in enumerate(values[1:], start=2):
        padded = list(raw) + [""] * (len(CONTENT_HEADERS) - len(raw))
        result.append((row_number, {CONTENT_HEADERS[i]: str(padded[i]) for i in range(len(CONTENT_HEADERS))}))
    return result


def enqueue_new_posts(service, spreadsheet_id, sheet_range, existing, current):
    bundled_posts = {
        str(x.get("post_urn", "")).strip()
        for x in existing
        if str(x.get("event_id", "")).startswith("COMMENT_BUNDLE:")
    }
    legacy_rows_by_post = {}
    for item in existing:
        post = str(item.get("post_urn", "")).strip()
        event_id = str(item.get("event_id", "")).strip()
        if post and event_id.startswith("COMMENT:") and not event_id.startswith("COMMENT_BUNDLE:"):
            legacy_rows_by_post.setdefault(post, []).append(item)
    created = 0
    for source_row, row in read_content_rows(service, spreadsheet_id, sheet_range):
        post_urn = str(row.get("LinkedIn Post ID", "")).strip()
        if str(row.get("LinkedIn Status", "")).strip().upper() != "PUBLISHED" or not post_urn:
            continue
        published_at = parse_dt(row.get("وقت آخر تشغيل", ""))
        if published_at is None or published_at < current - timedelta(hours=DISCOVERY_HOURS):
            continue
        if post_urn in bundled_posts:
            continue

        # Retire the earlier one-comment-per-post queue format before creating
        # the new bundle. No old queued comment is ever sent after migration.
        for legacy in legacy_rows_by_post.get(post_urn, []):
            if str(legacy.get("status", "")).upper() in {"PENDING", "RETRY", "BLOCKED_PERMISSION"}:
                update_event(
                    service, spreadsheet_id, int(legacy["_row_number"]),
                    {"status": "OBSOLETE_LEGACY_QUEUE", "updated_at": iso(current),
                     "last_error": "Superseded by the 3-7 comment bundle worker."},
                )

        count = choose_comment_count(post_urn)
        comments = generate_linkedin_comments(
            api_key=CONFIG["gemini_api_key"],
            model=CONFIG["gemini_model"],
            post_urn=post_urn,
            topic=row.get("الموضوع", ""),
            post=row.get("المحتوى", ""),
            legal_sources=row.get("المصادر القانونية", ""),
            count=count,
        )
        offsets = comment_schedule_offsets(count)
        bundle_id = f"COMMENT_BUNDLE:{post_urn}"
        for sequence, (message, offset) in enumerate(zip(comments, offsets), start=1):
            event_id = f"{bundle_id}:{sequence}"
            event = {
                "event_id": event_id,
                "source_row": str(source_row),
                "post_urn": post_urn,
                "topic": row.get("الموضوع", ""),
                "post_text": row.get("المحتوى", ""),
                "legal_sources": row.get("المصادر القانونية", ""),
                "action": "COMMENT",
                "sequence": str(sequence),
                "scheduled_at": iso(current + timedelta(minutes=offset)),
                "status": "PENDING",
                "comment_text": message,
                "attempts": "0",
                "capability_status": "NOT_CHECKED",
                "fingerprint": comment_fingerprint(post_urn, message),
                "created_at": iso(current),
                "updated_at": iso(current),
                "dry_run": "true" if DRY_RUN else "false",
            }
            append_event(service, spreadsheet_id, event)
        bundled_posts.add(post_urn)
        created += count
        print(f"Queued {count} contextual LinkedIn comments for {post_urn}")
    return created


def select_due(existing, current):
    due = []
    per_post = {}
    for row in existing:
        if str(row.get("status", "")).upper() not in {"PENDING", "RETRY"}:
            continue
        scheduled = parse_dt(row.get("scheduled_at", ""))
        if not scheduled or scheduled > current:
            continue
        post = row.get("post_urn", "")
        if per_post.get(post, 0) >= MAX_COMMENTS_PER_POST_PER_RUN:
            continue
        due.append(row)
        per_post[post] = per_post.get(post, 0) + 1
    return due


def main():
    print("=" * 72)
    print("KHYRAT LINKEDIN ENGAGEMENT WORKER")
    print("=" * 72)
    global CONFIG, DRY_RUN
    CONFIG = load_engagement_config()
    DRY_RUN = os.getenv("KHYRAT_LINKEDIN_ENGAGEMENT_DRY_RUN", "false").strip().lower() in {"1", "true", "yes", "on"}
    service = create_service(CONFIG["service_account_info"])
    ensure_engagement_sheet(service, CONFIG["sheet_id"])
    current = now_cairo()
    existing = read_engagement_rows(service, CONFIG["sheet_id"])

    if DRY_RUN:
        print("DRY RUN enabled: queue generation and comment text validation run, but no LinkedIn API write occurs.")

    created = enqueue_new_posts(service, CONFIG["sheet_id"], CONFIG["sheet_range"], existing, current)
    print(f"Queue events created: {created}")

    existing = read_engagement_rows(service, CONFIG["sheet_id"])
    due = select_due(existing, current)
    print(f"Due events: {len(due)}")
    if not due:
        return 0

    token = CONFIG["linkedin_access_token"]
    actor = (CONFIG.get("linkedin_author_urn", "") or "").strip() or resolve_member_urn(token)

    for event in due:
        row_number = int(event["_row_number"])
        attempts = int(event.get("attempts", "0") or "0") + 1
        if not event.get("comment_text"):
            update_event(service, CONFIG["sheet_id"], row_number, {
                "status": "FAILED", "last_error": "Queue row has no generated comment text.",
                "attempts": str(attempts), "updated_at": iso(current)
            })
            continue
        if DRY_RUN:
            update_event(service, CONFIG["sheet_id"], row_number, {
                "status": "DRY_RUN_READY", "attempts": str(attempts),
                "capability_status": "SKIPPED_DRY_RUN",
                "last_error": "DRY RUN: no LinkedIn comment was sent.",
                "updated_at": iso(current)
            })
            print(f"DRY RUN ready: {event['event_id']}")
            continue

        result = add_linkedin_comment(
            token=token, actor_urn=actor, post_urn=event["post_urn"],
            message=event["comment_text"], dry_run=False
        )
        changes = {
            "attempts": str(attempts),
            "last_http_status": str(result.http_status or ""),
            "last_error": str(result.error or "")[:1500],
            "updated_at": iso(current),
        }
        if result.status == "PUBLISHED":
            changes.update({
                "status": "PUBLISHED",
                "comment_urn": result.item_id,
                "last_error": "",
            })
        elif result.http_status == 403 or result.status == "DISABLED_PERMISSION":
            changes.update({
                "status": "BLOCKED_PERMISSION",
                "scheduled_at": iso(current + timedelta(hours=PERMISSION_RECHECK_HOURS)),
            })
        elif result.http_status == 401:
            changes.update({
                "status": "BLOCKED_TOKEN",
                "scheduled_at": iso(current + timedelta(hours=PERMISSION_RECHECK_HOURS)),
            })
        elif attempts >= MAX_ATTEMPTS:
            changes.update({"status": "FAILED"})
        else:
            changes.update({
                "status": "RETRY",
                "scheduled_at": iso(current + timedelta(minutes=RETRY_MINUTES)),
            })
        update_event(service, CONFIG["sheet_id"], row_number, changes)
        print(f"{event['event_id']} -> {changes['status']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
