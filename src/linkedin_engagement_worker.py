from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from comment_engine import generate_comments
from config import load_engagement_config
from linkedin_engagement import (
    add_linkedin_comment,
    check_comment_capability,
    comment_fingerprint,
)
from linkedin_publisher import resolve_member_urn
from sheets import create_service, get_values, sheet_name_from_range

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
COLUMNS = "T"
CAIRO = ZoneInfo("Africa/Cairo")
MAX_ATTEMPTS = int(os.getenv("LINKEDIN_ENGAGEMENT_MAX_ATTEMPTS", "3") or "3")
DELAY_MINUTES = int(os.getenv("LINKEDIN_ENGAGEMENT_DELAY_MINUTES", "15") or "15")
RETRY_MINUTES = int(os.getenv("LINKEDIN_ENGAGEMENT_RETRY_MINUTES", "30") or "30")
PERMISSION_RECHECK_HOURS = int(os.getenv("LINKEDIN_PERMISSION_RECHECK_HOURS", "24") or "24")


def now_cairo() -> datetime:
    return datetime.now(CAIRO)


def iso(dt: datetime) -> str:
    return dt.astimezone(CAIRO).isoformat()


def parse_dt(value: str) -> datetime | None:
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


def col_letter(n: int) -> str:
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def sheet_exists(service, spreadsheet_id: str, title: str) -> bool:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
    return any(str(s.get("properties", {}).get("title", "")).strip().casefold() == title.casefold() for s in meta.get("sheets", []))


def ensure_engagement_sheet(service, spreadsheet_id: str) -> None:
    if not sheet_exists(service, spreadsheet_id, ENGAGEMENT_SHEET):
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": ENGAGEMENT_SHEET}}}]},
        ).execute()
    last = col_letter(len(ENGAGEMENT_HEADERS))
    current = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{ENGAGEMENT_SHEET}!A1:{last}1",
    ).execute().get("values", [])
    if not current or current[0][:len(ENGAGEMENT_HEADERS)] != ENGAGEMENT_HEADERS:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{ENGAGEMENT_SHEET}!A1:{last}1",
            valueInputOption="RAW",
            body={"values": [ENGAGEMENT_HEADERS]},
        ).execute()


def read_engagement_rows(service, spreadsheet_id: str) -> list[dict[str, str]]:
    last = col_letter(len(ENGAGEMENT_HEADERS))
    values = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{ENGAGEMENT_SHEET}!A1:{last}",
        majorDimension="ROWS",
    ).execute().get("values", [])
    rows = []
    for idx, raw in enumerate(values[1:], start=2):
        padded = list(raw) + [""] * (len(ENGAGEMENT_HEADERS) - len(raw))
        item = {ENGAGEMENT_HEADERS[i]: str(padded[i]) for i in range(len(ENGAGEMENT_HEADERS))}
        item["_row_number"] = str(idx)
        rows.append(item)
    return rows


def append_event(service, spreadsheet_id: str, event: dict[str, str]) -> None:
    last = col_letter(len(ENGAGEMENT_HEADERS))
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{ENGAGEMENT_SHEET}!A:{last}",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [[event.get(h, "") for h in ENGAGEMENT_HEADERS]]},
    ).execute()


def update_event(service, spreadsheet_id: str, row_number: int, changes: dict[str, str]) -> None:
    last = col_letter(len(ENGAGEMENT_HEADERS))
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{ENGAGEMENT_SHEET}!A{row_number}:{last}{row_number}",
    ).execute().get("values", [])
    row = list(response[0]) if response else []
    row += [""] * (len(ENGAGEMENT_HEADERS) - len(row))
    for key, value in changes.items():
        if key in ENGAGEMENT_HEADERS:
            row[ENGAGEMENT_HEADERS.index(key)] = str(value)
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{ENGAGEMENT_SHEET}!A{row_number}:{last}{row_number}",
        valueInputOption="RAW",
        body={"values": [row[:len(ENGAGEMENT_HEADERS)]]},
    ).execute()


def read_content_rows(service, spreadsheet_id: str, sheet_range: str) -> list[tuple[int, dict[str, str]]]:
    values = get_values(service, spreadsheet_id, sheet_range)
    result = []
    for row_number, raw in enumerate(values[1:], start=2):
        padded = list(raw) + [""] * (len(CONTENT_HEADERS) - len(raw))
        result.append((row_number, {CONTENT_HEADERS[i]: str(padded[i]) for i in range(len(CONTENT_HEADERS))}))
    return result


def enqueue_new_posts(service, spreadsheet_id: str, sheet_range: str, existing: list[dict[str, str]], current: datetime) -> int:
    existing_events = {str(x.get("event_id", "")).strip() for x in existing if x.get("event_id")}
    known_posts = {
        str(x.get("post_urn", "")).strip()
        for x in existing
        if str(x.get("action", "")).strip().upper() == "COMMENT"
    }
    created = 0
    for source_row, row in read_content_rows(service, spreadsheet_id, sheet_range):
        post_urn = str(row.get("LinkedIn Post ID", "")).strip()
        if str(row.get("LinkedIn Status", "")).strip().upper() != "PUBLISHED" or not post_urn:
            continue
        event_id = f"COMMENT:{post_urn}:1"
        if event_id in existing_events or post_urn in known_posts:
            continue
        event = {
            "event_id": event_id,
            "source_row": str(source_row),
            "post_urn": post_urn,
            "topic": row.get("الموضوع", ""),
            "post_text": row.get("المحتوى", ""),
            "legal_sources": row.get("المصادر القانونية", ""),
            "action": "COMMENT",
            "sequence": "1",
            "scheduled_at": iso(current + timedelta(minutes=DELAY_MINUTES)),
            "status": "PENDING",
            "attempts": "0",
            "capability_status": "NOT_CHECKED",
            "fingerprint": "",
            "created_at": iso(current),
            "updated_at": iso(current),
            "dry_run": "true" if os.getenv("KHYRAT_LINKEDIN_ENGAGEMENT_DRY_RUN", "false").lower() in {"1", "true", "yes", "on"} else "false",
        }
        append_event(service, spreadsheet_id, event)
        existing_events.add(event_id)
        known_posts.add(post_urn)
        created += 1
    return created


def select_due(existing: list[dict[str, str]], current: datetime) -> list[dict[str, str]]:
    due = []
    for row in existing:
        status = str(row.get("status", "")).upper()
        if status not in {"PENDING", "RETRY", "BLOCKED_PERMISSION"}:
            continue
        scheduled = parse_dt(row.get("scheduled_at", ""))
        if scheduled and scheduled <= current:
            due.append(row)
    return due


def main() -> int:
    print("=" * 72)
    print("KHYRAT LINKEDIN ENGAGEMENT WORKER")
    print("=" * 72)

    config = load_engagement_config()
    service = create_service(config["service_account_info"])
    sheet_range = config["sheet_range"]
    ensure_engagement_sheet(service, config["sheet_id"])

    current = now_cairo()
    existing = read_engagement_rows(service, config["sheet_id"])
    created = enqueue_new_posts(service, config["sheet_id"], sheet_range, existing, current)
    print(f"Queue discovery: created={created}")

    # Refresh after enqueue so newly created events are visible in the same run.
    existing = read_engagement_rows(service, config["sheet_id"])
    due = select_due(existing, current)
    print(f"Due events: {len(due)}")
    if not due:
        return 0

    token = config["linkedin_access_token"]
    dry_run = os.getenv("KHYRAT_LINKEDIN_ENGAGEMENT_DRY_RUN", "false").strip().lower() in {"1", "true", "yes", "on"}
    capability = check_comment_capability(token=token)
    print(f"Capability: {capability.status} http={capability.http_status}")

    if capability.status == "BLOCKED_PERMISSION":
        for event in due:
            row_number = int(event["_row_number"])
            update_event(
                service, config["sheet_id"], row_number,
                {
                    "status": "BLOCKED_PERMISSION",
                    "capability_status": capability.status,
                    "last_http_status": str(capability.http_status),
                    "last_error": capability.error[:1500],
                    "scheduled_at": iso(current + timedelta(hours=PERMISSION_RECHECK_HOURS)),
                    "updated_at": iso(current),
                },
            )
        print("Comment permission is blocked; publisher remains unaffected.")
        return 0

    if capability.status in {"UNAUTHORIZED_TOKEN", "NETWORK_FAILED", "TRANSIENT_FAILURE"}:
        for event in due:
            row_number = int(event["_row_number"])
            update_event(
                service, config["sheet_id"], row_number,
                {
                    "status": "RETRY",
                    "capability_status": capability.status,
                    "last_http_status": str(capability.http_status),
                    "last_error": capability.error[:1500],
                    "scheduled_at": iso(current + timedelta(minutes=RETRY_MINUTES)),
                    "updated_at": iso(current),
                },
            )
        return 0

    actor = (config.get("linkedin_author_urn", "") or "").strip() or resolve_member_urn(token)
    for event in due:
        row_number = int(event["_row_number"])
        attempts = int(event.get("attempts", "0") or "0") + 1
        try:
            generated = generate_comments(
                api_key=config["gemini_api_key"],
                model=config["gemini_model"],
                topic=event.get("topic", ""),
                post=event.get("post_text", ""),
                legal_sources=event.get("legal_sources", ""),
            )
            comments = generated.get("linkedin_comments", [])
            if not comments:
                raise RuntimeError("Comment engine returned no LinkedIn comments.")
            message = comments[0].strip()
            fingerprint = comment_fingerprint(event["post_urn"], message)

            if dry_run:
                update_event(
                    service, config["sheet_id"], row_number,
                    {
                        "status": "DRY_RUN_READY",
                        "comment_text": message,
                        "attempts": str(attempts),
                        "capability_status": capability.status,
                        "fingerprint": fingerprint,
                        "last_error": "DRY RUN: no LinkedIn comment was sent.",
                        "updated_at": iso(current),
                    },
                )
                print(f"DRY RUN: prepared comment for {event['post_urn']}")
                continue

            result = add_linkedin_comment(
                token=token,
                actor_urn=actor,
                post_urn=event["post_urn"],
                message=message,
                dry_run=False,
            )
            if result.status == "PUBLISHED":
                update_event(
                    service, config["sheet_id"], row_number,
                    {
                        "status": "PUBLISHED",
                        "comment_text": message,
                        "comment_urn": result.item_id,
                        "attempts": str(attempts),
                        "last_http_status": str(result.http_status or ""),
                        "last_error": "",
                        "capability_status": capability.status,
                        "fingerprint": fingerprint,
                        "updated_at": iso(current),
                    },
                )
                print(f"Comment published: {result.item_id}")
                continue

            if result.http_status == 403 or result.status == "DISABLED_PERMISSION":
                status = "BLOCKED_PERMISSION"
                next_time = current + timedelta(hours=PERMISSION_RECHECK_HOURS)
            elif attempts >= MAX_ATTEMPTS:
                status = "FAILED"
                next_time = current
            else:
                status = "RETRY"
                next_time = current + timedelta(minutes=RETRY_MINUTES)

            update_event(
                service, config["sheet_id"], row_number,
                {
                    "status": status,
                    "comment_text": message,
                    "attempts": str(attempts),
                    "last_http_status": str(result.http_status or ""),
                    "last_error": str(result.error or "")[:1500],
                    "capability_status": capability.status,
                    "fingerprint": fingerprint,
                    "scheduled_at": iso(next_time),
                    "updated_at": iso(current),
                },
            )
        except Exception as exc:
            status = "FAILED" if attempts >= MAX_ATTEMPTS else "RETRY"
            update_event(
                service, config["sheet_id"], row_number,
                {
                    "status": status,
                    "attempts": str(attempts),
                    "last_error": str(exc)[:1500],
                    "scheduled_at": iso(current + timedelta(minutes=RETRY_MINUTES)),
                    "updated_at": iso(current),
                },
            )
            print(f"Engagement event failed: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
