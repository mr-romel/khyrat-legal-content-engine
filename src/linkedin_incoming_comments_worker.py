from __future__ import annotations

import os
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from comment_moderation import classify_comment, build_public_reply
from config import load_engagement_config
from linkedin_publisher import resolve_member_urn, LINKEDIN_REST_BASE
from sheets import create_service, get_values

CAIRO = ZoneInfo("Africa/Cairo")
SHEET_NAME = os.getenv("LINKEDIN_INCOMING_REPLY_SHEET", "LinkedIn Incoming Replies").strip()
HEADERS = [
    "event_id", "post_urn", "comment_urn", "comment_id", "actor_urn",
    "comment_text", "category", "intent", "confidence", "reply_policy",
    "suggested_reply", "reply_status", "reply_id", "http_status", "error", "created_at",
]
MAX_POSTS = max(1, int(os.getenv("LINKEDIN_INCOMING_MAX_POSTS", "10") or "10"))
MAX_COMMENTS = max(1, int(os.getenv("LINKEDIN_INCOMING_MAX_COMMENTS", "15") or "15"))


def _headers(token, version):
    return {
        "Authorization": f"Bearer {token}",
        "Linkedin-Version": version,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }


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
    rows = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{SHEET_NAME}!A2:{last}"
    ).execute().get("values", [])
    return {str(row[2]).strip() for row in rows if len(row) > 2 and str(row[2]).strip()}


def append_event(sheets, spreadsheet_id, event):
    last = _col(len(HEADERS))
    sheets.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range=f"{SHEET_NAME}!A:{last}",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [[event.get(key, "") for key in HEADERS]]},
    ).execute()


def run():
    cfg = load_engagement_config()
    token = cfg["linkedin_access_token"]
    version = os.getenv("LINKEDIN_VERSION", "202607").strip()
    actor = resolve_member_urn(token)
    sheets = create_service(cfg["service_account_info"])
    ensure_sheet(sheets, cfg["sheet_id"])
    seen = read_seen(sheets, cfg["sheet_id"])
    values = get_values(sheets, cfg["sheet_id"], "Content!A:BC")
    if not values:
        print("LinkedIn incoming comments: Content sheet is empty.")
        return 0
    headers = [str(x or "").strip() for x in values[0]]
    posts = []
    for row_number, raw in enumerate(values[1:], start=2):
        row = {headers[i]: str(raw[i] or "") for i in range(min(len(headers), len(raw)))}
        post_urn = str(row.get("LinkedIn Post ID", "")).strip()
        status = str(row.get("LinkedIn Status", "")).strip().upper()
        if post_urn and status == "PUBLISHED":
            posts.append((row_number, post_urn, row))
    posts = posts[-MAX_POSTS:]
    processed = 0
    for row_number, post_urn, row in reversed(posts):
        endpoint = f"{LINKEDIN_REST_BASE}/socialActions/{quote(post_urn, safe='')}/comments"
        try:
            response = requests.get(endpoint, headers=_headers(token, version), timeout=35)
        except requests.RequestException as exc:
            print(f"LinkedIn comment read network failure for post={post_urn}: {exc}")
            continue
        if response.status_code in {401, 403}:
            print(f"LINKEDIN_INCOMING_READ_BLOCKED: HTTP {response.status_code}; API permission r_member_social_feed or r_organization_social_feed may be unavailable. No replies were attempted.")
            return 0
        if not response.ok:
            print(f"LinkedIn comment read failed: HTTP {response.status_code} {response.text[:800]}")
            continue
        try:
            elements = response.json().get("elements", [])
        except ValueError:
            print("LinkedIn comment read returned invalid JSON.")
            continue
        for comment in elements:
            if processed >= MAX_COMMENTS:
                break
            comment_urn = str(comment.get("commentUrn", "")).strip()
            comment_id = str(comment.get("id", "")).strip()
            commenter = str(comment.get("actor", "")).strip()
            message = str((comment.get("message") or {}).get("text", "")).strip()
            if not comment_urn or not comment_id or comment_urn in seen or commenter == actor:
                continue
            decision = classify_comment(message)
            suggested = build_public_reply(decision)
            reply_status = "REVIEW_REQUIRED" if decision.action == "REVIEW" else ("SKIPPED_SPAM" if decision.action == "SKIP" else "PENDING")
            reply_id = ""
            http_status = ""
            error = decision.reason if decision.action != "AUTO_REPLY" else ""
            if decision.action == "AUTO_REPLY":
                reply_endpoint = f"{LINKEDIN_REST_BASE}/socialActions/{quote(comment_urn, safe='')}/comments"
                body = {
                    "actor": actor,
                    "object": post_urn,
                    "parentComment": comment_urn,
                    "message": {"text": suggested},
                }
                try:
                    reply_response = requests.post(reply_endpoint, headers=_headers(token, version), json=body, timeout=40)
                    http_status = str(reply_response.status_code)
                    if reply_response.ok:
                        reply_id = str(reply_response.headers.get("x-restli-id", "")).strip()
                        reply_status = "REPLIED" if reply_id else "REPLIED_UNVERIFIED"
                    else:
                        reply_status = "FAILED"
                        error = reply_response.text[:1000]
                except requests.RequestException as exc:
                    reply_status = "FAILED"
                    error = str(exc)[:1000]
            event = {
                "event_id": "LI_INCOMING_REPLY:" + comment_id,
                "post_urn": post_urn, "comment_urn": comment_urn, "comment_id": comment_id,
                "actor_urn": commenter, "comment_text": message, "category": decision.category,
                "intent": decision.intent, "confidence": str(decision.confidence),
                "reply_policy": decision.action, "suggested_reply": suggested,
                "reply_status": reply_status, "reply_id": reply_id,
                "http_status": http_status, "error": error,
                "created_at": datetime.now(CAIRO).isoformat(),
            }
            append_event(sheets, cfg["sheet_id"], event)
            seen.add(comment_urn)
            processed += 1
            print(f"LinkedIn incoming comment={comment_id} category={decision.category} status={reply_status} http={http_status}")
        if processed >= MAX_COMMENTS:
            break
    print(f"LinkedIn incoming comments processed={processed} across {len(posts)} published posts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
