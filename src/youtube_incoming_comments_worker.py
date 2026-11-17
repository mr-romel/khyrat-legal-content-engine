from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from comment_moderation import classify_comment, build_public_reply
from config import load_video_config
from sheets import create_service, get_values

CAIRO = ZoneInfo("Africa/Cairo")
SHEET_NAME = os.getenv("YOUTUBE_INCOMING_REPLY_SHEET", "YouTube Incoming Replies").strip()
HEADERS = [
    "event_id", "video_id", "comment_id", "author", "comment_text",
    "category", "intent", "confidence", "reply_policy", "suggested_reply",
    "reply_status", "reply_id", "error", "created_at",
]
MAX_VIDEOS = max(1, int(os.getenv("YOUTUBE_INCOMING_MAX_VIDEOS", "12") or "12"))
MAX_COMMENTS = max(1, int(os.getenv("YOUTUBE_INCOMING_MAX_COMMENTS", "15") or "15"))


def youtube_service():
    client_id = (os.getenv("YOUTUBE_COMMENT_CLIENT_ID") or os.getenv("YOUTUBE_CLIENT_ID", "")).strip()
    client_secret = (os.getenv("YOUTUBE_COMMENT_CLIENT_SECRET") or os.getenv("YOUTUBE_CLIENT_SECRET", "")).strip()
    refresh_token = os.getenv("YOUTUBE_COMMENT_REFRESH_TOKEN", "").strip()
    if not all((client_id, client_secret, refresh_token)):
        raise RuntimeError("YouTube incoming comments require the dedicated youtube.force-ssl OAuth grant.")
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token, "grant_type": "refresh_token"},
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"YouTube OAuth refresh failed: HTTP {response.status_code} {response.text[:500]}")
    token = response.json().get("access_token", "")
    if not token:
        raise RuntimeError("YouTube OAuth refresh returned no access token.")
    credentials = Credentials(
        token=token, refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id, client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def _col(n):
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def ensure_tracking_sheet(sheets, spreadsheet_id):
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


def read_existing(sheets, spreadsheet_id):
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
    cfg = load_video_config()
    sheets = create_service(cfg["service_account_info"])
    ensure_tracking_sheet(sheets, cfg["sheet_id"])
    seen = read_existing(sheets, cfg["sheet_id"])
    values = get_values(sheets, cfg["sheet_id"], "Content!A:BZ")
    if not values:
        print("YouTube incoming comments: Content sheet is empty.")
        return 0
    headers = [str(x or "").strip() for x in values[0]]
    candidates = []
    for row_number, raw in enumerate(values[1:], start=2):
        row = {headers[i]: str(raw[i] or "") for i in range(min(len(headers), len(raw)))}
        video_id = str(row.get("Reel YouTube ID", "")).strip()
        status = str(row.get("Reel Status", "")).strip().upper()
        if video_id and status in {"PUBLISHED", "SUCCESS", "POSTED"}:
            candidates.append((row_number, video_id, row))
    candidates = candidates[-MAX_VIDEOS:]
    yt = youtube_service()
    channel_response = yt.channels().list(part="id", mine=True).execute()
    channel_items = channel_response.get("items", [])
    if not channel_items:
        raise RuntimeError("YouTube OAuth identity returned no owned channel.")
    own_channel_id = str(channel_items[0].get("id", "")).strip()
    processed = 0
    for row_number, video_id, row in reversed(candidates):
        try:
            response = yt.commentThreads().list(
                part="snippet", videoId=video_id, maxResults=100, order="time", textFormat="plainText"
            ).execute()
        except Exception as exc:
            print(f"YouTube comments read blocked for video={video_id}: {exc}")
            continue
        for thread in response.get("items", []):
            if processed >= MAX_COMMENTS:
                break
            snippet = thread.get("snippet", {}).get("topLevelComment", {})
            comment_id = str(snippet.get("id", "")).strip()
            body = snippet.get("snippet", {}) or {}
            author = str(body.get("authorDisplayName", "")).strip()
            author_channel = str((body.get("authorChannelId") or {}).get("value", "")).strip()
            comment_text = str(body.get("textOriginal") or body.get("textDisplay") or "").strip()
            if not comment_id or comment_id in seen or author_channel == own_channel_id:
                continue
            decision = classify_comment(comment_text)
            suggested = build_public_reply(decision)
            status = "REVIEW_REQUIRED" if decision.action == "REVIEW" else ("SKIPPED_SPAM" if decision.action == "SKIP" else "PENDING")
            reply_id = ""
            error = ""
            if decision.action == "AUTO_REPLY":
                try:
                    result = yt.comments().insert(
                        part="snippet",
                        body={"snippet": {"parentId": comment_id, "textOriginal": suggested}},
                    ).execute()
                    reply_id = str(result.get("id", "")).strip()
                    if not reply_id:
                        raise RuntimeError("YouTube returned no reply comment ID.")
                    status = "REPLIED"
                except Exception as exc:
                    status = "FAILED"
                    error = str(exc)[:1000]
            elif decision.action == "REVIEW":
                error = decision.reason
            elif decision.action == "SKIP":
                error = decision.reason
            event = {
                "event_id": "YT_INCOMING_REPLY:" + comment_id,
                "video_id": video_id, "comment_id": comment_id, "author": author,
                "comment_text": comment_text, "category": decision.category,
                "intent": decision.intent, "confidence": str(decision.confidence),
                "reply_policy": decision.action, "suggested_reply": suggested,
                "reply_status": status, "reply_id": reply_id, "error": error,
                "created_at": datetime.now(CAIRO).isoformat(),
            }
            append_event(sheets, cfg["sheet_id"], event)
            seen.add(comment_id)
            processed += 1
            print(f"YouTube incoming comment={comment_id} category={decision.category} status={status} reply_id={reply_id}")
        if processed >= MAX_COMMENTS:
            break
    print(f"YouTube incoming comment worker processed={processed} across {len(candidates)} published Shorts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
