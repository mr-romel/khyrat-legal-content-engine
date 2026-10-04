from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from config import load_facebook_engagement_config
from facebook_publisher import like_comment, reply_to_comment
from sheets import create_service, get_values

# This worker intentionally handles PUBLIC threaded replies only.
# It never sends private messages.
SHEET_NAME = os.getenv("FACEBOOK_COMMENT_REPLY_SHEET", "Facebook Comment Replies").strip() or "Facebook Comment Replies"
HEADERS = [
    "event_id", "post_id", "comment_id", "commenter_id", "commenter_name",
    "post_topic", "comment_text", "like_status", "like_http_status",
    "reply_status", "reply_id", "reply_text", "reply_http_status",
    "last_error", "created_at", "updated_at", "platform_proof",
]
CAIRO = ZoneInfo("Africa/Cairo")
MAX_RECENT_POSTS = int(os.getenv("FACEBOOK_COMMENT_REPLY_RECENT_POSTS", "3") or "3")
MAX_COMMENTS_PER_RUN = int(os.getenv("FACEBOOK_COMMENT_REPLY_MAX_COMMENTS_PER_RUN", "5") or "5")
MAX_COMMENT_AGE_HOURS = int(os.getenv("FACEBOOK_COMMENT_REPLY_MAX_COMMENT_AGE_HOURS", "168") or "168")
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
        payload = response.json()
        error = payload.get("error", payload) if isinstance(payload, dict) else payload
        if isinstance(error, dict):
            return (
                f"message={error.get('message', '')}; "
                f"code={error.get('code', '')}; "
                f"subcode={error.get('error_subcode', '')}; "
                f"fbtrace_id={error.get('fbtrace_id', '')}"
            )
        return str(error)
    except ValueError:
        return response.text[:1500]


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
        "fields": "id,message,from,created_time,can_comment,user_likes,parent",
        "filter": "toplevel",
        "order": "reverse_chronological",
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


def build_public_reply(comment_text, post_topic, index):
    # Keep the public reply short and human. The request is deliberately limited
    # to thanks + follow + share; it does not pretend to provide legal advice.
    text = str(comment_text or "").strip()
    topic = str(post_topic or "").strip()
    topic_hint = ""
    if any(k in f"{topic} {text}" for k in ("عمل", "عامل", "موظف", "فصل", "مرتب", "إجاز")):
        topic_hint = "محتوى قانون العمل"
    elif any(k in f"{topic} {text}" for k in ("شركة", "شركات", "عقد", "عقود")):
        topic_hint = "المحتوى القانوني للشركات والعقود"
    elif any(k in f"{topic} {text}" for k in ("إيجار", "إيجارات", "مالك", "مستأجر")):
        topic_hint = "محتوى الإيجارات والمواقف العملية"
    else:
        topic_hint = "المحتوى القانوني المبسط"

    templates = [
        f"شكرًا جدًا على تعليقك. سعيد إن {topic_hint} أفادك. تابع صفحة اسأل محمود علشان توصلك المنشورات الجديدة، ولو شايف البوست مفيد شاركه مع حد ممكن يستفيد.",
        f"شكرًا على تفاعلك. تابع اسأل محمود للمزيد من {topic_hint}، ولو المعلومة مهمة بالنسبة لك شارك البوست مع غيرك علشان الفائدة توصل لأكبر عدد.",
        f"كل الشكر على تعليقك. تابع الصفحة علشان توصلك المعلومة القانونية الجديدة أولًا بأول، ولو البوست مفيد شاركه مع شخص ممكن يحتاجه.",
        f"شكرًا لتفاعلك معنا. تابع صفحة اسأل محمود واستمر في متابعتنا للمحتوى القانوني العملي، ومشاركتك للبوست بتساعد المعلومة توصل لناس أكتر.",
        f"شكرًا على تعليقك. تابع الصفحة علشان تشوف الجديد من اسأل محمود، ولو شايف المحتوى مفيد شاركه مع أصحابك أو زملائك.",
    ]
    return templates[index % len(templates)]


def _event_id(comment_id):
    return "COMMENT_REPLY:" + hashlib.sha256(comment_id.encode("utf-8")).hexdigest()[:24]


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
    completed_ids = {
        str(x.get("comment_id", "")).strip()
        for x in existing
        if str(x.get("comment_id", "")).strip()
        and str(x.get("reply_status", "")).upper() in {"REPLIED", "REPLIED_UNVERIFIED", "SKIPPED_ALREADY_REPLIED"}
    }

    posts = recent_posts(service, sheet_id, sheet_range)
    print(f"Facebook public comment reply scope: latest {len(posts)} post(s)")
    if not posts:
        return 0

    processed = 0
    for _published_at_value, source_row, post_id, post_row in posts:
        comments, http_status, error = list_comments(post_id, token)
        if error:
            print(f"Comment discovery failed for {post_id}: http={http_status} error={error}")
            continue

        print(f"Facebook comment discovery: post={post_id} comments={len(comments)}")

        for comment in comments:
            if processed >= MAX_COMMENTS_PER_RUN:
                break

            comment_id = str(comment.get("id", "")).strip()
            if not comment_id or comment_id in completed_ids:
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

            # Never act on the Page's own public comments.
            if commenter_id and commenter_id == page_id:
                continue

            # If Meta explicitly says this comment cannot be replied to, do not
            # waste a write call. Missing can_comment is treated as unknown and
            # the reply is attempted so older field responses remain compatible.
            can_comment = comment.get("can_comment")
            if can_comment is False:
                print(f"Public reply not eligible: {comment_id} | can_comment=False")
                continue

            like_result = {"status": "SKIPPED_ALREADY_LIKED", "http_status": ""}
            if comment.get("user_likes") is not True:
                like_result = like_comment(
                    comment_id=comment_id,
                    page_access_token=token,
                    graph_version=GRAPH_VERSION,
                )

            reply_text = build_public_reply(
                comment.get("message", ""),
                post_row.get("الموضوع", ""),
                processed,
            )
            reply_result = reply_to_comment(
                comment_id=comment_id,
                page_access_token=token,
                graph_version=GRAPH_VERSION,
                message=reply_text,
            )

            errors = []
            if like_result.get("status") not in {"LIKED", "SKIPPED_ALREADY_LIKED"}:
                errors.append(f"LIKE: {like_result.get('error', '')}")
            if reply_result.get("status") not in {"REPLIED", "REPLIED_UNVERIFIED"}:
                errors.append(f"REPLY: {reply_result.get('error', '')}")

            event = {
                "event_id": _event_id(comment_id),
                "post_id": post_id,
                "comment_id": comment_id,
                "commenter_id": commenter_id,
                "commenter_name": commenter_name,
                "post_topic": post_row.get("الموضوع", ""),
                "comment_text": str(comment.get("message", "")),
                "like_status": like_result.get("status", ""),
                "like_http_status": like_result.get("http_status", ""),
                "reply_status": reply_result.get("status", ""),
                "reply_id": reply_result.get("reply_id", ""),
                "reply_text": reply_text,
                "reply_http_status": reply_result.get("http_status", ""),
                "last_error": " | ".join(errors),
                "created_at": iso(current),
                "updated_at": iso(current),
                "platform_proof": reply_result.get("platform_proof", "") or like_result.get("platform_proof", ""),
            }
            append_row(service, sheet_id, event)
            completed_ids.add(comment_id)
            processed += 1

            print(
                f"{event['event_id']} -> like={event['like_status']} reply={event['reply_status']} "
                f"| comment={comment_id} | like_http={event['like_http_status']} "
                f"reply_http={event['reply_http_status']} | error={event['last_error']}"
            )

        if processed >= MAX_COMMENTS_PER_RUN:
            break

    print(f"Facebook public comment reply worker processed={processed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
