from __future__ import annotations

import hashlib
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from blogger_publisher import blog_id, service as blogger_service
from comment_moderation import classify_comment, build_public_reply
from config import load_blogger_config
from sheets import create_service

CAIRO = ZoneInfo("Africa/Cairo")
SHEET_NAME = os.getenv("BLOGGER_INCOMING_REPLY_SHEET", "Blogger Incoming Replies").strip()
HEADERS = [
    "event_id", "comment_id", "post_id", "post_title", "post_url",
    "author", "comment_text", "category", "intent", "confidence",
    "reply_policy", "suggested_reply", "reply_status", "error", "created_at",
]
MAX_COMMENTS = max(1, int(os.getenv("BLOGGER_INCOMING_MAX_COMMENTS", "100") or "100"))


def _col(n):
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def ensure_sheet(sheets, spreadsheet_id):
    meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
    if not any(str(x.get("properties", {}).get("title", "")).casefold() == SHEET_NAME.casefold() for x in meta.get("sheets", [])):
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": SHEET_NAME}}}]},
        ).execute()
    last = _col(len(HEADERS))
    current = sheets.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=f"{SHEET_NAME}!A1:{last}1").execute().get("values", [])
    if not current or current[0][:len(HEADERS)] != HEADERS:
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"{SHEET_NAME}!A1:{last}1",
            valueInputOption="RAW", body={"values": [HEADERS]},
        ).execute()


def read_seen(sheets, spreadsheet_id):
    last = _col(len(HEADERS))
    rows = sheets.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=f"{SHEET_NAME}!A2:{last}").execute().get("values", [])
    return {str(row[1]).strip() for row in rows if len(row) > 1 and str(row[1]).strip()}


def append_event(sheets, spreadsheet_id, event):
    last = _col(len(HEADERS))
    sheets.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range=f"{SHEET_NAME}!A:{last}",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [[event.get(key, "") for key in HEADERS]]},
    ).execute()


def run():
    cfg = load_blogger_config()
    if not cfg.get("enabled"):
        print("Blogger comments: BLOGGER_ENABLED is false; read-only scan skipped.")
        return 0
    bid = blog_id()
    if not bid:
        raise RuntimeError("Blogger blog ID is not configured.")
    api = blogger_service()
    sheets = create_service(cfg["service_account_info"])
    ensure_sheet(sheets, cfg["sheet_id"])
    seen = read_seen(sheets, cfg["sheet_id"])
    page_token = None
    comments = []
    while len(comments) < MAX_COMMENTS:
        response = api.comments().listByBlog(
            blogId=bid, fetchBodies=True, status="live", maxResults=min(100, MAX_COMMENTS - len(comments)),
            pageToken=page_token,
        ).execute()
        comments.extend(response.get("items", []) or [])
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    processed = 0
    for comment in comments:
        comment_id = str(comment.get("id", "")).strip()
        if not comment_id or comment_id in seen:
            continue
        post_id = str((comment.get("post") or {}).get("id", "")).strip()
        author = str((comment.get("author") or {}).get("displayName", "")).strip()
        text = str(comment.get("content", "")).strip()
        post_title = ""
        post_url = ""
        if post_id:
            try:
                post = api.posts().get(blogId=bid, postId=post_id).execute()
                post_title = str(post.get("title", "")).strip()
                post_url = str(post.get("url", "")).strip()
            except Exception as exc:
                print(f"Blogger comment context lookup failed for post={post_id}: {exc}")
        decision = classify_comment(text)
        suggested = build_public_reply(decision)
        status = "REVIEW_REQUIRED" if decision.action == "REVIEW" else ("SKIPPED_SPAM" if decision.action == "SKIP" else "READY_TO_REPLY_MANUALLY")
        # Blogger API v3 exposes comment list/get/moderation operations but no insert/reply method.
        # Never fake a published reply: keep the approved draft in the queue for the Blogger UI.
        event = {
            "event_id": "BLOGGER_INCOMING_REPLY:" + hashlib.sha256(comment_id.encode("utf-8")).hexdigest()[:24],
            "comment_id": comment_id, "post_id": post_id, "post_title": post_title, "post_url": post_url,
            "author": author, "comment_text": text, "category": decision.category,
            "intent": decision.intent, "confidence": str(decision.confidence),
            "reply_policy": decision.action, "suggested_reply": suggested,
            "reply_status": status, "error": "Blogger API v3 has no comment insert/reply method; publish via Blogger UI.",
            "created_at": datetime.now(CAIRO).isoformat(),
        }
        append_event(sheets, cfg["sheet_id"], event)
        seen.add(comment_id)
        processed += 1
    print(f"Blogger incoming comments classified={processed}; replies remain manual in Blogger UI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
