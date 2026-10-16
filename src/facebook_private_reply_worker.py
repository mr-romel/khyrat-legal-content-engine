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
MAX_RECENT_POSTS = int(os.getenv("FACEBOOK_COMMENT_REPLY_RECENT_POSTS", "60") or "60")
MAX_COMMENTS_PER_RUN = int(os.getenv("FACEBOOK_COMMENT_REPLY_MAX_COMMENTS_PER_RUN", "50") or "50")
MAX_COMMENT_AGE_HOURS = int(os.getenv("FACEBOOK_COMMENT_REPLY_MAX_COMMENT_AGE_HOURS", "8760") or "8760")
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


def _include_reel_columns(sheet_range: str) -> str:
    """Widen the usual A:AF content range so Reel Facebook ID is not truncated."""
    match = re.match(r"^(.*!A:)([A-Z]+)$", str(sheet_range or "").strip())
    if not match:
        return sheet_range
    end_column = match.group(2)
    end_index = 0
    for char in end_column:
        end_index = end_index * 26 + ord(char) - ord("A") + 1
    # BC is column 55. Preserve any configured range that is already wider.
    return f"{match.group(1)}{end_column if end_index >= 55 else 'BC'}"


def recent_posts(service, spreadsheet_id, sheet_range):
    """Return recent Facebook feed posts AND published Reels from the content sheet."""
    candidates = []
    seen_ids = set()
    current = now()
    for source_row, row in read_content(service, spreadsheet_id, sheet_range):
        published_at = _published_at(row, current)
        source_row = int(source_row)

        post_id = str(row.get("Facebook Post ID", "")).strip()
        post_status = str(row.get("Facebook Status", "")).strip().upper()
        if post_id and post_status == "PUBLISHED" and post_id not in seen_ids:
            seen_ids.add(post_id)
            candidates.append((published_at, source_row, post_id, row))

        # Reel fields live after AF in the content sheet. The workflow must read
        # through BC so the Reel Facebook ID is actually available to this worker.
        reel_id = str(row.get("Reel Facebook ID", "")).strip()
        reel_status = str(row.get("Reel Status", "")).strip().upper()
        if reel_id and reel_status == "PUBLISHED" and reel_id not in seen_ids:
            seen_ids.add(reel_id)
            candidates.append((published_at, source_row, reel_id, row))

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    print(
        "Facebook reply targets discovered: "
        f"posts={sum(1 for item in candidates if str(item[3].get('Facebook Post ID', '')).strip() == item[2])} "
        f"reels={sum(1 for item in candidates if str(item[3].get('Reel Facebook ID', '')).strip() == item[2])}"
    )
    return candidates[:MAX_RECENT_POSTS]


def list_comments(post_id, token):
    """Read all available top-level comments across Graph API pages.

    A single 50-comment page silently skipped older comments whenever a post
    or Reel had a busy thread. Bound pagination to keep a scheduled run finite.
    """
    params = {
        "access_token": token,
        "fields": "id,message,from,created_time,can_comment,user_likes,parent,comment_count",
        "filter": "toplevel",
        "order": "reverse_chronological",
        "limit": "100",
    }
    url = graph_url(post_id, "comments")
    comments = []
    last_status = 200
    # Up to 10 pages / 1,000 comments per post per run; newest comments first.
    for _page in range(10):
        try:
            response = requests.get(url, params=params, timeout=45)
        except requests.RequestException as exc:
            return comments, 0, str(exc)
        last_status = response.status_code
        if not response.ok:
            return comments, response.status_code, api_error(response)
        try:
            payload = response.json()
        except ValueError:
            return comments, response.status_code, "Facebook returned invalid JSON while listing comments."
        comments.extend(payload.get("data", []) or [])
        paging = payload.get("paging") or {}
        cursors = paging.get("cursors") or {}
        after = str(cursors.get("after", "")).strip()
        if not paging.get("next") or not after:
            break
        # Keep the token in params rather than reusing a paging URL that may
        # expose credentials in logs or persist it outside this request.
        params["after"] = after
    return comments, last_status, ""


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
    sheet_range = _include_reel_columns(config["sheet_range"])
    print(f"Facebook comment worker sheet range: {sheet_range}")
    current = now()

    ensure_sheet(service, sheet_id)
    existing = read_rows(service, sheet_id)
    # Keep the latest attempt for each comment. A successful reply must not
    # suppress a retry for a failed like (and vice versa).
    existing_by_comment = {}
    for item in existing:
        comment_id = str(item.get("comment_id", "")).strip()
        if comment_id:
            existing_by_comment[comment_id] = item
    reply_done_states = {"REPLIED", "REPLIED_UNVERIFIED", "SKIPPED_ALREADY_REPLIED", "SKIPPED_NOT_REPLYABLE"}
    like_done_states = {"LIKED", "SKIPPED_ALREADY_LIKED"}

    posts = recent_posts(service, sheet_id, sheet_range)
    print(f"Facebook public comment reply scope: latest {len(posts)} post(s)")
    if not posts:
        return 0

    processed = 0
    skipped_age = 0
    skipped_not_replyable = 0
    skipped_page = 0
    skipped_completed = 0
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
            if not comment_id:
                continue
            previous = existing_by_comment.get(comment_id, {})
            previous_reply_status = str(previous.get("reply_status", "")).upper()
            previous_like_status = str(previous.get("like_status", "")).upper()
            reply_done = previous_reply_status in reply_done_states
            like_done = previous_like_status in like_done_states
            if reply_done and like_done:
                skipped_completed += 1
                continue

            created_text = str(comment.get("created_time", "")).strip()
            try:
                created = datetime.fromisoformat(created_text.replace("Z", "+00:00")).astimezone(CAIRO)
            except ValueError:
                created = current

            if current - created > timedelta(hours=MAX_COMMENT_AGE_HOURS):
                skipped_age += 1
                continue

            author = comment.get("from") or {}
            commenter_id = str(author.get("id", "")).strip() if isinstance(author, dict) else ""
            commenter_name = str(author.get("name", "")).strip() if isinstance(author, dict) else ""

            # Never act on the Page's own public comments.
            if commenter_id and commenter_id == page_id:
                skipped_page += 1
                continue

            # Like and reply are independent actions: retry only whichever failed.
            if like_done:
                like_result = {
                    "status": previous_like_status,
                    "http_status": previous.get("like_http_status", ""),
                    "platform_proof": "",
                }
            elif comment.get("user_likes") is True:
                like_result = {"status": "SKIPPED_ALREADY_LIKED", "http_status": ""}
            else:
                like_result = like_comment(
                    comment_id=comment_id,
                    page_access_token=token,
                    graph_version=GRAPH_VERSION,
                )

            can_comment = comment.get("can_comment")
            if reply_done:
                reply_text = str(previous.get("reply_text", "") or "")
                reply_result = {
                    "status": previous_reply_status,
                    "reply_id": previous.get("reply_id", ""),
                    "http_status": previous.get("reply_http_status", ""),
                    "platform_proof": previous.get("platform_proof", ""),
                }
            elif can_comment is False:
                skipped_not_replyable += 1
                reply_text = ""
                reply_result = {
                    "status": "SKIPPED_NOT_REPLYABLE",
                    "http_status": "",
                    "error": "Meta marked this comment as not replyable.",
                }
                print(f"Public reply not eligible; comment may still be liked: {comment_id}")
            else:
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
            existing_by_comment[comment_id] = event
            processed += 1

            print(
                f"{event['event_id']} -> like={event['like_status']} reply={event['reply_status']} "
                f"| comment={comment_id} | like_http={event['like_http_status']} "
                f"reply_http={event['reply_http_status']} | error={event['last_error']}"
            )

        if processed >= MAX_COMMENTS_PER_RUN:
            break

    print(
        f"Facebook public comment reply worker processed={processed} | "
        f"completed={skipped_completed} | age={skipped_age} | "
        f"page={skipped_page} | not_replyable={skipped_not_replyable}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
