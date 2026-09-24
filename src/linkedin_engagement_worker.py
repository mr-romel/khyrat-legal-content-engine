from __future__ import annotations

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import load_engagement_config
from linkedin_comment_engine import choose_comment_count, comment_schedule_offsets, generate_linkedin_comments
from linkedin_engagement import add_linkedin_comment, comment_fingerprint
from linkedin_publisher import like_comment, like_post, resolve_member_urn
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
DISCOVERY_HOURS = int(os.getenv("LINKEDIN_ENGAGEMENT_DISCOVERY_HOURS", "24") or "24")
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


def _published_at_from_row(row):
    # The publication schedule is the stable source for ordering posts.
    # Support common sheet display formats and never use "وقت آخر تشغيل"
    # when schedule fields are present but malformed; that field is an
    # execution timestamp and can make an old post look newer than it is.
    date_text = str(row.get("تاريخ النشر", "")).strip()
    time_text = str(row.get("ساعة النشر", "")).strip()
    if date_text and time_text:
        import re
        date_match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_text)
        time_match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", time_text)
        if date_match and time_match:
            try:
                from datetime import date, time as dt_time
                parsed_date = date(
                    int(date_match.group(1)),
                    int(date_match.group(2)),
                    int(date_match.group(3)),
                )
                parsed_time = dt_time(
                    int(time_match.group(1)),
                    int(time_match.group(2)),
                    int(time_match.group(3) or 0),
                )
                return datetime.combine(parsed_date, parsed_time, tzinfo=CAIRO)
            except (ValueError, TypeError):
                return None
        return None
    return parse_dt(row.get("وقت آخر تشغيل", ""))


def enqueue_new_posts(service, spreadsheet_id, sheet_range, existing, current):
    bundled_posts = {
        str(x.get("post_urn", "")).strip()
        for x in existing
        if str(x.get("event_id", "")).startswith("COMMENT_BUNDLE:")
    }
    # The latest post that has actually received a comment is the watermark.
    # Never fall back to an older post once a newer post has been commented.
    commented_posts = {
        str(x.get("post_urn", "")).strip()
        for x in existing
        if str(x.get("action", "")).upper() == "COMMENT"
        and str(x.get("status", "")).upper() == "PUBLISHED"
        and str(x.get("post_urn", "")).strip()
    }
    legacy_rows_by_post = {}
    for item in existing:
        post = str(item.get("post_urn", "")).strip()
        event_id = str(item.get("event_id", "")).strip()
        if post and event_id.startswith("COMMENT:") and not event_id.startswith("COMMENT_BUNDLE:"):
            legacy_rows_by_post.setdefault(post, []).append(item)

    candidates = []
    for source_row, row in read_content_rows(service, spreadsheet_id, sheet_range):
        post_urn = str(row.get("LinkedIn Post ID", "")).strip()
        if str(row.get("LinkedIn Status", "")).strip().upper() != "PUBLISHED" or not post_urn:
            continue
        published_at = _published_at_from_row(row)
        # If schedule fields exist but are malformed, do not let the execution
        # timestamp masquerade as publication time. Skip that row for ordering.
        if published_at is None and str(row.get("تاريخ النشر", "")).strip() and str(row.get("ساعة النشر", "")).strip():
            print(f"Skipping published LinkedIn row {source_row}: invalid schedule date/time; date={row.get('تاريخ النشر', '')!r}; time={row.get('ساعة النشر', '')!r}")
            continue
        # Rows with no schedule fields at all can still be recovered using
        # current time plus sheet position as the fallback ordering signal.
        if published_at is None:
            published_at = current
        candidates.append((published_at, source_row, row, post_urn))

    if not candidates:
        return 0

    candidates.sort(key=lambda item: (item[0], int(item[1])), reverse=True)
    if candidates:
        latest_debug = candidates[0]
        print(f"Newest eligible LinkedIn post: row={latest_debug[1]}, published_at={latest_debug[0].isoformat()}, post_id={latest_debug[3]!r}")

    # Only the newest eligible post is allowed to start a comment bundle.
    # This prevents a missed/old post from creating a backlog behind the latest post.
    latest_published_at, source_row, row, post_urn = candidates[0]

    if post_urn in bundled_posts:
        bundle_rows = [x for x in existing if str(x.get("post_urn", "")).strip() == post_urn and str(x.get("event_id", "")).startswith("COMMENT_BUNDLE:")]
        has_reaction = any(str(x.get("action", "")).upper() == "REACTION" for x in bundle_rows)
        if not has_reaction:
            reaction_event = {
                "event_id": f"COMMENT_BUNDLE:{post_urn}:REACTION",
                "source_row": str(source_row),
                "post_urn": post_urn,
                "topic": row.get("الموضوع", ""),
                "post_text": row.get("المحتوى", ""),
                "legal_sources": row.get("المصادر القانونية", ""),
                "action": "REACTION",
                "sequence": "0",
                "scheduled_at": iso(current),
                "status": "PENDING",
                "comment_text": "",
                "attempts": "0",
                "capability_status": "NOT_CHECKED",
                "fingerprint": comment_fingerprint(post_urn, "__LIKE_POST__"),
                "created_at": iso(current),
                "updated_at": iso(current),
                "dry_run": "true" if DRY_RUN else "false",
            }
            append_event(service, spreadsheet_id, reaction_event)
            print(f"Added missing reaction event for existing bundle: {post_urn}")
        return 0

    # If an older post was the last one to receive a comment, the newest post
    # is still allowed through. Older candidates are never backfilled.
    if commented_posts:
        commented_times = {
            p: next((item[0] for item in candidates if item[3] == p), None)
            for p in commented_posts
        }
        known_times = [t for t in commented_times.values() if t is not None]
        if known_times and latest_published_at <= max(known_times):
            return 0

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

    # Schedule comments from publication with a 15-minute gap.
    # There is intentionally no one-hour cutoff: 3-7 comments may span
    # beyond the first hour while the worker still publishes at most one
    # new comment per 15-minute cycle.
    base_time = latest_published_at

    reaction_event = {
        "event_id": f"{bundle_id}:REACTION",
        "source_row": str(source_row),
        "post_urn": post_urn,
        "topic": row.get("الموضوع", ""),
        "post_text": row.get("المحتوى", ""),
        "legal_sources": row.get("المصادر القانونية", ""),
        "action": "REACTION",
        "sequence": "0",
        "scheduled_at": iso(current),
        "status": "PENDING",
        "comment_text": "",
        "attempts": "0",
        "capability_status": "NOT_CHECKED",
        "fingerprint": comment_fingerprint(post_urn, "__LIKE_POST__"),
        "created_at": iso(current),
        "updated_at": iso(current),
        "dry_run": "true" if DRY_RUN else "false",
    }
    append_event(service, spreadsheet_id, reaction_event)

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
            "scheduled_at": iso(base_time + timedelta(minutes=offset)),
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
    print(
        f"Queued {count} contextual LinkedIn comments for {post_urn} "
        "15-minute spaced schedule"
    )
    return count

def select_due(existing, current):
    due = []
    per_post_comments = {}
    for row in existing:
        if str(row.get("status", "")).upper() not in {"PENDING", "RETRY"}:
            continue
        scheduled = parse_dt(row.get("scheduled_at", ""))
        if not scheduled or scheduled > current:
            continue
        action = str(row.get("action", "COMMENT")).upper()
        post = row.get("post_urn", "")
        if action == "COMMENT":
            if per_post_comments.get(post, 0) >= MAX_COMMENTS_PER_POST_PER_RUN:
                continue
            per_post_comments[post] = per_post_comments.get(post, 0) + 1
        elif action not in {"REACTION", "COMMENT_LIKE"}:
            continue
        due.append(row)

    # A single worker cycle publishes at most one new comment for the newest
    # post. This is the key guard against multiple queued comments dropping
    # together when several scheduled_at values are already overdue.
    comments = [x for x in due if str(x.get("action", "")).upper() == "COMMENT"]
    non_comments = [x for x in due if str(x.get("action", "")).upper() != "COMMENT"]
    if comments:
        comments.sort(key=lambda x: (parse_dt(x.get("scheduled_at", "")) or current, int(x.get("_row_number", "0"))))
        due = non_comments + comments[:1]
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
        action = str(event.get("action", "COMMENT")).upper()
        if action not in {"COMMENT", "REACTION", "COMMENT_LIKE"}:
            update_event(service, CONFIG["sheet_id"], row_number, {
                "status": "FAILED", "last_error": f"Unsupported engagement action: {action}",
                "attempts": str(attempts), "updated_at": iso(current)
            })
            continue
        if action == "COMMENT" and not event.get("comment_text"):
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

        if action == "REACTION":
            result = like_post(
                token=token, actor_urn=actor, post_urn=event["post_urn"]
            )
        elif action == "COMMENT_LIKE":
            result = like_comment(
                token=token, actor_urn=actor, comment_urn=event["comment_urn"]
            )
        else:
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
        if result.status in {"PUBLISHED", "LIKED"}:
            changes.update({
                "status": result.status,
                "comment_urn": result.item_id if action == "COMMENT" else event.get("comment_urn", ""),
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

        # Immediately queue a durable like-on-comment event after a successful
        # comment. It is processed on the next worker cycle if it cannot be
        # completed in this cycle, so a transient failure cannot cause a lost
        # comment-like and a rerun cannot duplicate it.
        if action == "COMMENT" and result.status == "PUBLISHED" and result.item_id:
            like_event_id = f"{event['event_id']}:LIKE"
            existing_like = any(
                str(x.get("event_id", "")).strip() == like_event_id
                for x in existing
            )
            if not existing_like:
                like_event = {
                    "event_id": like_event_id,
                    "source_row": event.get("source_row", ""),
                    "post_urn": event.get("post_urn", ""),
                    "topic": event.get("topic", ""),
                    "post_text": event.get("post_text", ""),
                    "legal_sources": event.get("legal_sources", ""),
                    "action": "COMMENT_LIKE",
                    "sequence": event.get("sequence", ""),
                    "scheduled_at": iso(current),
                    "status": "PENDING",
                    "comment_text": "",
                    "comment_urn": result.item_id,
                    "attempts": "0",
                    "capability_status": "NOT_CHECKED",
                    "fingerprint": comment_fingerprint(result.item_id, "__LIKE_COMMENT__"),
                    "created_at": iso(current),
                    "updated_at": iso(current),
                    "dry_run": "true" if DRY_RUN else "false",
                }
                append_event(service, CONFIG["sheet_id"], like_event)
                print(f"{like_event_id} -> PENDING")

        print(f"{event['event_id']} -> {changes['status']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
