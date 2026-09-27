from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from config import load_facebook_engagement_config
from sheets import create_service, get_values

SHEET_NAME = os.getenv("FACEBOOK_PRIVATE_REPLY_SHEET", "Facebook Private Replies").strip() or "Facebook Private Replies"
HEADERS = [
    "event_id", "post_id", "comment_id", "commenter_id", "commenter_name",
    "post_topic", "comment_text", "message", "status", "http_status",
    "last_error", "created_at", "updated_at", "platform_proof",
]
CAIRO = ZoneInfo("Africa/Cairo")
MAX_RECENT_POSTS = int(os.getenv("FACEBOOK_PRIVATE_REPLY_RECENT_POSTS", "3") or "3")
MAX_COMMENTS_PER_RUN = int(os.getenv("FACEBOOK_PRIVATE_REPLY_MAX_COMMENTS_PER_RUN", "5") or "5")
MAX_COMMENT_AGE_HOURS = int(os.getenv("FACEBOOK_PRIVATE_REPLY_MAX_COMMENT_AGE_HOURS", "168") or "168")
GRAPH_VERSION = os.getenv("FACEBOOK_GRAPH_VERSION", "26.0").strip().lstrip("v")


def now():
    return datetime.now(CAIRO)


def iso(dt):
    return dt.astimezone(CAIRO).isoformat()


def col_letter(n):
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def graph_url(object_id, edge=""):
    suffix = f"/{edge.lstrip('/')}" if edge else ""
    return f"https://graph.facebook.com/v{GRAPH_VERSION}/{object_id}{suffix}"


def api_error(response):
    try:
        return str(response.json())
    except ValueError:
        return response.text[:1000]


def ensure_sheet(service, spreadsheet_id):
    last = col_letter(len(HEADERS))
    meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties"
    ).execute()
    exists = any(
        str(s.get("properties", {}).get("title", "")).strip().casefold() == SHEET_NAME.casefold()
        for s in meta.get("sheets", [])
    )
    if not exists:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": SHEET_NAME}}}]},
        ).execute()
    current = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{SHEET_NAME}!A1:{last}1"
    ).execute().get("values", [])
    if not current or current[0][:len(HEADERS)] != HEADERS:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{SHEET_NAME}!A1:{last}1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()


def read_rows(service, spreadsheet_id):
    last = col_letter(len(HEADERS))
    values = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET_NAME}!A1:{last}",
    ).execute().get("values", [])
    rows = []
    for raw in values[1:]:
        padded = list(raw) + [""] * (len(HEADERS) - len(raw))
        rows.append({HEADERS[i]: str(padded[i]) for i in range(len(HEADERS))})
    return rows


def append_row(service, spreadsheet_id, event):
    last = col_letter(len(HEADERS))
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET_NAME}!A:{last}",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [[event.get(h, "") for h in HEADERS]]},
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
    if not values:
        return []
    headers = list(values[0])
    rows = []
    for row_number, raw in enumerate(values[1:], start=2):
        padded = list(raw) + [""] * (len(headers) - len(raw))
        rows.append((row_number, {str(headers[i]): str(padded[i]) for i in range(len(headers))}))
    return rows


def recent_posts(service, spreadsheet_id, sheet_range):
    candidates = []
    for source_row, row in read_content(service, spreadsheet_id, sheet_range):
        post_id = str(row.get("Facebook Post ID", "")).strip()
        if str(row.get("Facebook Status", "")).strip().upper() != "PUBLISHED" or not post_id:
            continue
        candidates.append((_published_at(row, now()), int(source_row), post_id, row))
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[:MAX_RECENT_POSTS]


def list_comments(post_id, token):
    params = {
        "access_token": token,
        "fields": "id,message,from,created_time,can_reply_privately,private_reply_conversation",
        "limit": "50",
    }
    try:
        response = requests.get(graph_url(post_id, "comments"), params=params, timeout=45)
    except requests.RequestException as exc:
        return [], 0, str(exc)
    if not response.ok:
        return [], response.status_code, api_error(response)
    payload = response.json()
    return payload.get("data", []) or [], response.status_code, ""


def build_message(topic, post_text):
    topic = str(topic or "").strip()
    text = str(post_text or "").strip()
    low = f"{topic} {text}".lower()
    if any(k in low for k in ["عمل", "عمال", "موظف", "فصل", "مرتب", "إجاز"]):
        context = "بننشر باستمرار محتوى مبسط عن قانون العمل وحقوق العامل وصاحب العمل"
    elif any(k in low for k in ["إيجار", "إيجارات", "مالك", "مستأجر"]):
        context = "بننشر باستمرار محتوى مبسط عن الإيجارات والمشكلات القانونية العملية"
    elif any(k in low for k in ["شركة", "شركات", "عقد", "عقود"]):
        context = "بننشر باستمرار محتوى عملي عن الشركات والعقود وحماية الحقوق"
    else:
        context = "بننشر باستمرار محتوى قانوني مبسط عن الحقوق والإجراءات والمواقف العملية"
    return f"أهلًا بك، وشكرًا على تفاعلك. {context}. تابع الصفحة علشان توصلك المنشورات الجديدة وتستفيد من المحتوى القانوني."


def send_private_reply(comment_id, token, message):
    try:
        response = requests.post(
            graph_url(comment_id, "private_replies"),
            data={"access_token": token, "message": message},
            timeout=45,
        )
    except requests.RequestException as exc:
        return {"status": "NETWORK_FAILED", "http_status": 0, "error": str(exc)}
    if response.ok:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return {
            "status": "SENT",
            "http_status": response.status_code,
            "proof": f"LIVE_PRIVATE_REPLY:{comment_id}",
            "raw": payload,
        }
    return {
        "status": "FAILED",
        "http_status": response.status_code,
        "error": api_error(response),
    }


def main():
    config = load_facebook_engagement_config()
    service = create_service(config["service_account_info"])
    token = config["facebook_page_access_token"]
    page_id = config["facebook_page_id"]
    sheet_id = config["sheet_id"]
    sheet_range = config["sheet_range"]
    current = now()

    ensure_sheet(service, sheet_id)
    existing = read_rows(service, sheet_id)
    sent_ids = {
        str(x.get("comment_id", "")).strip()
        for x in existing
        if str(x.get("status", "")).upper() == "SENT"
    }

    posts = recent_posts(service, sheet_id, sheet_range)
    print(f"Facebook private-reply scope: latest {len(posts)} post(s)")
    if not posts:
        return 0

    processed = 0
    for published_at, source_row, post_id, post_row in posts:
        comments, http_status, error = list_comments(post_id, token)
        if error:
            print(f"Comment discovery failed for {post_id}: http={http_status} error={error}")
            continue

        for comment in comments:
            if processed >= MAX_COMMENTS_PER_RUN:
                break
            comment_id = str(comment.get("id", "")).strip()
            if not comment_id or comment_id in sent_ids:
                continue

            created_text = str(comment.get("created_time", "")).strip()
            try:
                created = datetime.fromisoformat(created_text.replace("Z", "+00:00")).astimezone(CAIRO)
            except ValueError:
                created = current

            if current - created > timedelta(hours=MAX_COMMENT_AGE_HOURS):
                continue

            author = comment.get("from") or {}
            commenter_id = str(author.get("id", "")).strip() if isinstance(author, dict) else ""
            commenter_name = str(author.get("name", "")).strip() if isinstance(author, dict) else ""

            # Never DM the Page's own comments.
            if commenter_id and commenter_id == page_id:
                continue

            can_reply = comment.get("can_reply_privately")
            if can_reply is not True:
                print(f"Private reply not eligible: {comment_id} | can_reply_privately={can_reply}")
                continue

            message = build_message(post_row.get("الموضوع", ""), post_row.get("المحتوى", ""))
            result = send_private_reply(comment_id, token, message)
            event_id = "PRIVATE_REPLY:" + hashlib.sha256(comment_id.encode()).hexdigest()[:24]

            event = {
                "event_id": event_id,
                "post_id": post_id,
                "comment_id": comment_id,
                "commenter_id": commenter_id,
                "commenter_name": commenter_name,
                "post_topic": post_row.get("الموضوع", ""),
                "comment_text": str(comment.get("message", "")),
                "message": message,
                "status": result["status"],
                "http_status": result.get("http_status", ""),
                "last_error": result.get("error", ""),
                "created_at": iso(current),
                "updated_at": iso(current),
                "platform_proof": result.get("proof", ""),
            }
            append_row(service, sheet_id, event)
            processed += 1

            print(
                f"{event_id} -> {result['status']} | comment={comment_id} | "
                f"http={result.get('http_status', '')}"
            )

        if processed >= MAX_COMMENTS_PER_RUN:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
