from __future__ import annotations

import json
from typing import Any

from comment_engine import generate_comments
from config import load_social_engagement_config
from facebook_publisher import add_comment as facebook_add_comment, like_post as facebook_like_post
from linkedin_publisher import add_comment as linkedin_add_comment, like_post as linkedin_like_post, resolve_member_urn
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row
from utils import sheet_name_from_range

MAX_COMMENTS = 7


def _queue(row: dict[str, str], key: str, *, config: dict[str, Any]) -> list[str]:
    raw = str(row.get(key, "") or "").strip()
    if raw:
        try:
            value = json.loads(raw)
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()][:MAX_COMMENTS]
        except json.JSONDecodeError:
            pass

    comments = generate_comments(
        api_key=config["gemini_api_key"],
        model=config["gemini_model"],
        topic=row.get("الموضوع", ""),
        post=row.get("المحتوى", ""),
        legal_sources=row.get("المصادر القانونية", ""),
    )
    return comments["facebook_comments"] if key == "Facebook Comment Queue" else comments["linkedin_comments"]


def _count(row: dict[str, str], key: str) -> int:
    try:
        return max(0, int(str(row.get(key, "0") or "0").strip()))
    except ValueError:
        return 0


def _set_queue_if_missing(service, config, sheet_name: str, row_number: int, row: dict[str, str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    if not str(row.get("Facebook Comment Queue", "") or "").strip():
        fb = _queue(row, "Facebook Comment Queue", config=config)
        updates["Facebook Comment Queue"] = json.dumps(fb, ensure_ascii=False)
        row["Facebook Comment Queue"] = updates["Facebook Comment Queue"]
    if not str(row.get("LinkedIn Comment Queue", "") or "").strip():
        li = _queue(row, "LinkedIn Comment Queue", config=config)
        updates["LinkedIn Comment Queue"] = json.dumps(li, ensure_ascii=False)
        row["LinkedIn Comment Queue"] = updates["LinkedIn Comment Queue"]
    if updates:
        update_row(service, config["sheet_id"], sheet_name, row_number, updates)
    return row


def _process_facebook(service, config, sheet_name: str, row_number: int, row: dict[str, str]) -> None:
    post_id = str(row.get("Facebook Post ID", "") or "").strip()
    if not post_id or str(row.get("Facebook Status", "")).strip().upper() != "PUBLISHED":
        return

    reaction_status = str(row.get("Facebook Reaction Status", "") or "").strip().upper()
    if reaction_status not in {"LIKED", "DISABLED_PERMISSION"}:
        result = facebook_like_post(
            post_id=post_id,
            page_access_token=config["facebook_page_access_token"],
            graph_version=config["facebook_graph_version"],
        )
        status = str(result.get("status", "FAILED")).upper()
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Facebook Reaction Status": status,
            "آخر خطأ": str(result.get("error", ""))[:1500],
        })
        if status != "LIKED":
            return

    queue = _queue(row, "Facebook Comment Queue", config=config)
    published = _count(row, "Facebook Comments Published")
    if published >= len(queue):
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Facebook Comment Status": "COMPLETE",
        })
        return

    result = facebook_add_comment(
        post_id=post_id,
        page_access_token=config["facebook_page_access_token"],
        graph_version=config["facebook_graph_version"],
        message=queue[published],
    )
    status = str(result.get("status", "FAILED")).upper()
    if status == "PUBLISHED":
        published += 1
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Facebook Comments Published": str(published),
            "Facebook Comment Status": "COMPLETE" if published >= len(queue) else "QUEUED",
            "Facebook Comment ID": str(result.get("comment_id", "")),
            "Facebook Like Status": str(result.get("like_status", "")),
            "آخر خطأ": str(result.get("like_error", ""))[:1500],
        })
    else:
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "Facebook Comment Status": "FAILED",
            "آخر خطأ": str(result.get("error", ""))[:1500],
        })


def _process_linkedin(service, config, sheet_name: str, row_number: int, row: dict[str, str]) -> None:
    post_urn = str(row.get("LinkedIn Post ID", "") or "").strip()
    if not post_urn or str(row.get("LinkedIn Status", "")).strip().upper() != "PUBLISHED":
        return

    token = config["linkedin_access_token"]
    actor = str(config.get("linkedin_author_urn", "") or "").strip() or resolve_member_urn(token)

    reaction_status = str(row.get("LinkedIn Reaction Status", "") or "").strip().upper()
    if reaction_status not in {"LIKED", "DISABLED_PERMISSION"}:
        result = linkedin_like_post(token=token, actor_urn=actor, post_urn=post_urn)
        status = result.status
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "LinkedIn Reaction Status": status,
            "آخر خطأ": result.error[:1500],
        })
        if status not in {"LIKED"}:
            return

    queue = _queue(row, "LinkedIn Comment Queue", config=config)
    published = _count(row, "LinkedIn Comments Published")
    if published >= len(queue):
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "LinkedIn Comment Status": "COMPLETE",
        })
        return

    result = linkedin_add_comment(
        token=token,
        actor_urn=actor,
        post_urn=post_urn,
        message=queue[published],
    )
    status = result.status
    if status == "PUBLISHED":
        published += 1
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "LinkedIn Comments Published": str(published),
            "LinkedIn Comment Status": "COMPLETE" if published >= len(queue) else "QUEUED",
            "آخر خطأ": "",
        })
    else:
        update_row(service, config["sheet_id"], sheet_name, row_number, {
            "LinkedIn Comment Status": status,
            "آخر خطأ": result.error[:1500],
        })


def main() -> None:
    config = load_social_engagement_config()
    service = create_service(config["service_account_info"])
    sheet_name = sheet_name_from_range(config["sheet_range"])
    ensure_headers(service, config["sheet_id"], sheet_name)
    values = get_values(service, config["sheet_id"], f"{sheet_name}!A:AF")
    if not values:
        print("Engagement worker: no rows found.")
        return

    rows = [row_to_dict(row) for row in values[1:]]
    for row_number, row in enumerate(rows, start=2):
        if str(row.get("الحالة", "")).strip().upper() not in {"PUBLISHED", "PARTIAL_FAILED"}:
            continue
        if not row.get("Facebook Post ID") and not row.get("LinkedIn Post ID"):
            continue
        try:
            row = _set_queue_if_missing(service, config, sheet_name, row_number, row)
            _process_facebook(service, config, sheet_name, row_number, row)
            _process_linkedin(service, config, sheet_name, row_number, row)
        except Exception as exc:
            print(f"Engagement worker row {row_number} failed: {exc}")


if __name__ == "__main__":
    main()
