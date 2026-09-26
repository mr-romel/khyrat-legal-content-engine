from __future__ import annotations

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import load_engagement_config
from linkedin_comment_engine import choose_comment_count, comment_schedule_offsets, generate_linkedin_comments
from linkedin_engagement import add_linkedin_comment, comment_fingerprint
from linkedin_publisher import like_comment, like_post, resolve_member_urn, verify_comment
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
    "created_at", "updated_at", "dry_run", "platform_proof", "verified_at",
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
    """Ensure every published LinkedIn post with unfinished engagement is queued."""
    candidates = []
    legacy_rows_by_post = {}
    for item in existing:
        post = str(item.get("post_urn", "")).strip()
        event_id = str(item.get("event_id", "")).strip()
        if post and event_id.startswith("COMMENT:") and not event_id.startswith("COMMENT_BUNDLE:"):
            legacy_rows_by_post.setdefault(post, []).append(item)

    for source_row, row in read_content_rows(service, spreadsheet_id, sheet_range):
        post_urn = str(row.get("LinkedIn Post ID", "")).strip()
        if str(row.get("LinkedIn Status", "")).strip().upper() != "PUBLISHED" or not post_urn:
            continue
        published_at = _published_at_from_row(row) or current
        candidates.append((published_at, source_row, row, post_urn))

    candidates.sort(key=lambda item: (item[0], int(item[1])), reverse=True)
    if candidates:
        print(f"Published LinkedIn posts eligible for engagement: {len(candidates)}")

    created = 0
    for published_at, source_row, row, post_urn in candidates:
        post_events = [x for x in existing if str(x.get("post_urn", "")).strip() == post_urn]
        bundle_id = f"COMMENT_BUNDLE:{post_urn}"

        # Migrate any old one-comment queue rows away from the new bundle format.
        for legacy in legacy_rows_by_post.get(post_urn, []):
            if str(legacy.get("status", "")).upper() in {"PENDING", "RETRY", "BLOCKED_PERMISSION"}:
                update_event(
                    service, spreadsheet_id, int(legacy["_row_number"]),
                    {"status": "OBSOLETE_LEGACY_QUEUE", "updated_at": iso(current),
                     "last_error": "Superseded by the 3-7 comment bundle worker."},
                )

        reaction_id = f"{bundle_id}:REACTION"
        if not any(str(x.get("event_id", "")).strip() == reaction_id for x in post_events):
            append_event(service, spreadsheet_id, {
                "event_id": reaction_id,
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
            })
            created += 1

        target_count = choose_comment_count(f"{row.get('الموضوع', '')}|{row.get('المحتوى', '')}")
        published_count = sum(
            1 for x in post_events
            if str(x.get("action", "")).upper() == "COMMENT"
            and str(x.get("status", "")).upper() == "PUBLISHED"
        )
        queued_count = sum(
            1 for x in post_events
            if str(x.get("action", "")).upper() == "COMMENT"
            and str(x.get("status", "")).upper() in {"PENDING", "RETRY"}
        )
        missing = max(0, target_count - published_count - queued_count)
        if missing == 0:
            continue

        comments = generate_linkedin_comments(
            api_key=CONFIG["gemini_api_key"],
            model=CONFIG["gemini_model"],
            post_urn=post_urn,
            topic=row.get("الموضوع", ""),
            post=row.get("المحتوى", ""),
            legal_sources=row.get("المصادر القانونية", ""),
            count=missing,
        )
        offsets = comment_schedule_offsets(missing)
        existing_sequences = {
            int(x.get("sequence", "0") or "0")
            for x in post_events
            if str(x.get("action", "")).upper() == "COMMENT"
        }
        next_sequence = max(existing_sequences, default=0) + 1

        for offset_index, (message, offset) in enumerate(zip(comments, offsets)):
            sequence = next_sequence + offset_index
            append_event(service, spreadsheet_id, {
                "event_id": f"{bundle_id}:{sequence}",
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
            })
            created += 1
        print(f"Queued {missing} LinkedIn comments for {post_urn} ({published_count}/{target_count} already published)")

    return created

def release_legacy_permission_blocks(service, spreadsheet_id, existing, current):
    """Re-open queue items blocked by the old REST-first member path.

    Before the personal-member route was made primary, a 403 from the
    versioned REST socialActions endpoint could park an event for 24 hours.
    Those events must be retried immediately after the route fix; otherwise
    the old queue state would keep the worker silent even though the known
    member path is available.
    """
    released = 0
    for row in existing:
        status = str(row.get("status", "")).upper()
        if status != "BLOCKED_PERMISSION":
            continue
        action = str(row.get("action", "COMMENT")).upper()
        if action not in {"COMMENT", "REACTION", "COMMENT_LIKE"}:
            continue
        error = str(row.get("last_error", "")).lower()
        # Only release rows blocked by the previous REST-first implementation.
        # A current v2 permission failure remains blocked and follows the normal
        # 24-hour recheck policy.
        if action == "COMMENT" and "comment: http 403" not in error:
            continue
        if action == "REACTION" and "like: http 403" not in error:
            continue
        if action == "COMMENT_LIKE" and "like_comment: http 403" not in error:
            continue
        update_event(
            service,
            spreadsheet_id,
            int(row["_row_number"]),
            {
                "status": "RETRY",
                "scheduled_at": iso(current),
                "last_error": "Released from legacy REST permission block; retrying with personal member route.",
                "updated_at": iso(current),
            },
        )
        released += 1
    if released:
        print(f"Released {released} legacy LinkedIn permission-blocked event(s) for immediate retry.")
    return released


def release_one_time_reaction_retry(service, spreadsheet_id, existing, current):
    """Immediately retry the first reaction that was parked by the old route."""
    released = 0
    for row in existing:
        if str(row.get("action", "")).upper() != "REACTION":
            continue
        status = str(row.get("status", "")).upper()
        if status == "FAILED" and "http 409" in str(row.get("last_error", "")).lower():
            update_event(
                service,
                spreadsheet_id,
                int(row["_row_number"]),
                {
                    "status": "LIKED",
                    "last_error": "",
                    "capability_status": "RECOVERY_IDEMPOTENT_409",
                    "updated_at": iso(current),
                },
            )
            print("Marked LinkedIn post reaction as LIKED because LinkedIn returned HTTP 409 for an existing reaction.")
            released += 1
            break
        capability = str(row.get("capability_status", "")).upper()
        if status == "RETRY" and capability not in {"RECOVERY_RELEASED", "RECOVERY_FINAL_RELEASED"}:
            recovery_status = "RETRY"
            recovery_note = "One-time recovery retry after LinkedIn reaction API route upgrade."
        elif status == "FAILED" and capability in {"RECOVERY_RELEASED", "RECOVERY_DIAGNOSTIC_RELEASED"}:
            recovery_status = "RETRY"
            recovery_note = "Final idempotent reaction retry after LinkedIn 409 handling upgrade."
        else:
            continue
        update_event(
            service,
            spreadsheet_id,
            int(row["_row_number"]),
            {
                "status": recovery_status,
                "scheduled_at": iso(current),
                "last_error": recovery_note,
                "capability_status": "RECOVERY_FINAL_RELEASED",
                "updated_at": iso(current),
            },
        )
        released += 1
        break
    if released:
        print("Released one parked LinkedIn post-reaction for immediate retry.")
    return released


def reconcile_legacy_successes(service, spreadsheet_id, existing, current):
    """Re-open legacy successes that have no recorded LinkedIn API proof."""
    released = 0
    for row in existing:
        status = str(row.get("status", "")).upper()
        action = str(row.get("action", "")).upper()
        if status not in {"PUBLISHED", "LIKED"}:
            continue
        http_status = str(row.get("last_http_status", "")).strip()
        proof = str(row.get("platform_proof", "")).strip()
        comment_urn = str(row.get("comment_urn", "")).strip()
        if proof.startswith("LIVE_"):
            continue
        if action == "COMMENT" and comment_urn:
            verification = verify_comment(
                token=CONFIG["linkedin_access_token"],
                post_urn=str(row.get("post_urn", "")).strip(),
                comment_urn=comment_urn,
            )
            if verification.status == "VERIFIED":
                update_event(service, spreadsheet_id, int(row["_row_number"]), {
                    "platform_proof": f"LIVE_COMMENT_URN:{comment_urn}",
                    "last_http_status": verification.http_status or "",
                    "verified_at": iso(current),
                    "last_error": "",
                })
                print(f"LinkedIn comment verified: {comment_urn}")
            elif verification.status == "NOT_FOUND":
                update_event(service, spreadsheet_id, int(row["_row_number"]), {
                    "status": "RETRY",
                    "scheduled_at": iso(current),
                    "platform_proof": "",
                    "verified_at": "",
                    "last_http_status": verification.http_status or "",
                    "last_error": "Legacy LinkedIn comment no longer resolves; reopened for real publication.",
                    "updated_at": iso(current),
                })
                released += 1
            else:
                update_event(service, spreadsheet_id, int(row["_row_number"]), {
                    "platform_proof": f"LEGACY_COMMENT_URN:{comment_urn}",
                    "last_http_status": verification.http_status or "",
                    "verified_at": "",
                    "last_error": verification.error or "",
                })
                print(f"LinkedIn comment verification unavailable: {comment_urn} | http={verification.http_status}")
            continue
        update_event(service, spreadsheet_id, int(row["_row_number"]), {
            "status": "RETRY",
            "scheduled_at": iso(current),
            "last_error": "Legacy success had no recorded LinkedIn API proof; reopened for real API execution.",
            "capability_status": "RECONCILIATION_RELEASED",
            "updated_at": iso(current),
        })
        released += 1
    if released:
        print(f"LinkedIn legacy success reconciliation reopened {released} engagement event(s).")
    return released


def _bundle_post_ids(existing):
    posts = []
    seen = set()
    for row in existing:
        event_id = str(row.get("event_id", "")).strip()
        if not event_id.startswith("COMMENT_BUNDLE:"):
            continue
        post_urn = str(row.get("post_urn", "")).strip()
        if post_urn and post_urn not in seen:
            seen.add(post_urn)
            posts.append(post_urn)
    return posts

def _rebaseline_pending_comments(service, spreadsheet_id, existing, post_urn, anchor, interval_minutes=15):
    """Rebase remaining comments from the actual last successful publication."""
    pending = [
        row for row in existing
        if str(row.get("post_urn", "")).strip() == post_urn
        and str(row.get("action", "")).upper() == "COMMENT"
        and str(row.get("status", "")).upper() in {"PENDING", "RETRY"}
    ]
    pending.sort(key=lambda row: int(row.get("sequence", "0") or "0"))
    for index, row in enumerate(pending, start=1):
        target = anchor + timedelta(minutes=interval_minutes * index)
        current_scheduled = parse_dt(row.get("scheduled_at", ""))
        if current_scheduled is None or abs((current_scheduled - target).total_seconds()) > 1:
            update_event(
                service,
                spreadsheet_id,
                int(row["_row_number"]),
                {"scheduled_at": iso(target), "updated_at": iso(anchor)},
            )


def select_due(existing, current):
    known_posts = set(_bundle_post_ids(existing))
    due = []
    for row in existing:
        if str(row.get("post_urn", "")).strip() not in known_posts:
            continue
        if str(row.get("status", "")).upper() not in {"PENDING", "RETRY"}:
            continue
        scheduled = parse_dt(row.get("scheduled_at", ""))
        if not scheduled or scheduled > current:
            continue
        action = str(row.get("action", "COMMENT")).upper()
        if action not in {"COMMENT", "REACTION", "COMMENT_LIKE"}:
            continue
        due.append(row)

    non_comments = [x for x in due if str(x.get("action", "")).upper() != "COMMENT"]
    comments_by_post = {}
    for row in due:
        if str(row.get("action", "")).upper() == "COMMENT":
            comments_by_post.setdefault(str(row.get("post_urn", "")), []).append(row)
    selected_comments = []
    for post_urn, rows in comments_by_post.items():
        rows.sort(key=lambda x: (parse_dt(x.get("scheduled_at", "")) or current, int(x.get("_row_number", "0"))))
        selected_comments.append(rows[0])
    return non_comments + selected_comments

def _main_impl():
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

    release_legacy_permission_blocks(
        service,
        CONFIG["sheet_id"],
        existing,
        current,
    )
    existing = read_engagement_rows(service, CONFIG["sheet_id"])
    release_one_time_reaction_retry(
        service,
        CONFIG["sheet_id"],
        existing,
        current,
    )
    existing = read_engagement_rows(service, CONFIG["sheet_id"])
    reconcile_legacy_successes(service, CONFIG["sheet_id"], existing, current)
    existing = read_engagement_rows(service, CONFIG["sheet_id"])

    if DRY_RUN:
        print("DRY RUN enabled: queue generation and comment text validation run, but no LinkedIn API write occurs.")

    created = enqueue_new_posts(service, CONFIG["sheet_id"], CONFIG["sheet_range"], existing, current)
    print(f"Queue events created: {created}")

    existing = read_engagement_rows(service, CONFIG["sheet_id"])
    due = select_due(existing, current)
    print(f"Due events: {len(due)}")
    reaction_debug = [
        (str(x.get("event_id", "")), str(x.get("status", "")), str(x.get("attempts", "")), str(x.get("scheduled_at", "")), str(x.get("last_error", ""))[:180])
        for x in existing
        if str(x.get("action", "")).upper() == "REACTION"
    ]
    print(f"LinkedIn reaction queue: {reaction_debug[-5:]}")
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
            proof = f"LIVE_ITEM:{result.item_id}" if result.item_id else f"LIVE_HTTP:{result.http_status or ''}"
            if result.http_status == 409:
                proof = "LIVE_HTTP:409:IDEMPOTENT"
            changes.update({
                "status": result.status,
                "comment_urn": result.item_id if action == "COMMENT" else event.get("comment_urn", ""),
                "platform_proof": proof,
                "verified_at": iso(current),
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

        if action == "COMMENT" and result.status == "PUBLISHED":
            refreshed = read_engagement_rows(service, CONFIG["sheet_id"])
            _rebaseline_pending_comments(
                service,
                CONFIG["sheet_id"],
                refreshed,
                event["post_urn"],
                now_cairo(),
                interval_minutes=15,
            )

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

        print(
            f"{event['event_id']} -> {changes['status']} | "
            f"http={changes.get('last_http_status', '')} | error={changes.get('last_error', '')[:500]}"
        )

    return 0


def main():
    try:
        return _main_impl()
    except Exception as exc:
        # Engagement is strictly non-blocking. A failed comment worker must
        # never affect the publishing workflow or prevent the next retry cycle.
        print(f"Non-blocking engagement worker error: {exc}")
        import traceback
        print(traceback.format_exc())
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
