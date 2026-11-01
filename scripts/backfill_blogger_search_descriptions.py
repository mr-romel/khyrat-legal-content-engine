from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from blogger_publisher import DEFAULT_BLOG_URL, blog_id, service


def _plain_text(value: str) -> str:
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", str(value or ""), flags=re.I | re.S)
    value = re.sub(r"<br\s*/?>|</p\s*>|</li\s*>|</h[1-6]\s*>", ". ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip(" .\t\r\n")


def _first_paragraph(fragment: str) -> str:
    match = re.search(r"<p\b[^>]*>(.*?)</p\s*>", fragment, flags=re.I | re.S)
    return _plain_text(match.group(1) if match else fragment)


def build_search_description(content: str, title: str = "") -> str:
    """Derive a truthful snippet from the article's own concise answer or opening paragraph."""
    content = str(content or "")
    answer = re.search(
        r"<h[2-4]\b[^>]*>[^<]*(?:الإجابة المختصرة|ملخص الإجابة|الخلاصة)[^<]*</h[2-4]\s*>(.*?)(?=<h[1-4]\b|$)",
        content,
        flags=re.I | re.S,
    )
    candidate = _first_paragraph(answer.group(1)) if answer else ""
    if len(candidate) < 70:
        candidate = _first_paragraph(content)
    candidate = re.sub(r"^" + re.escape(str(title or "").strip()) + r"\s*[:：—-]?\s*", "", candidate, flags=re.I)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if len(candidate) <= 150:
        return candidate
    cut = candidate[:150]
    boundary = cut.rfind(" ")
    if boundary >= 115:
        cut = cut[:boundary]
    return cut.rstrip(" ،؛:—-") + "…"


def main() -> int:
    apply = os.getenv("BLOGGER_SEARCH_DESCRIPTION_APPLY", "false").strip().lower() in {"1", "true", "yes"}
    limit = max(1, min(500, int(os.getenv("BLOGGER_SEARCH_DESCRIPTION_LIMIT", "500"))))
    blog_url = os.getenv("BLOGGER_URL", DEFAULT_BLOG_URL).strip()
    svc = service()
    bid = blog_id(svc, blog_url)
    posts = []
    token = None
    while True:
        args = {"blogId": bid, "status": "LIVE", "fetchBodies": True, "maxResults": 500}
        if token:
            args["pageToken"] = token
        batch = svc.posts().list(**args).execute()
        posts.extend(batch.get("items") or [])
        token = batch.get("nextPageToken")
        if not token:
            break

    out = Path("artifacts/blogger-search-descriptions")
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = []
    report = {"run_id": stamp, "blog_url": blog_url, "live_posts": len(posts), "apply_mode": apply,
              "updated": [], "skipped": [], "errors": []}

    for post in posts[:limit]:
        post_id = str(post.get("id", "")).strip()
        title = str(post.get("title", "")).strip()
        old_description = str(post.get("searchDescription", "") or "").strip()
        content = str(post.get("content", "") or "")
        new_description = build_search_description(content, title)
        backup.append({"id": post_id, "title": title, "url": post.get("url", ""),
                       "old_searchDescription": old_description, "new_searchDescription": new_description})
        if old_description:
            report["skipped"].append({"id": post_id, "title": title, "reason": "existing searchDescription preserved"})
            continue
        if len(new_description) < 70:
            report["skipped"].append({"id": post_id, "title": title, "reason": "insufficient grounded text for safe snippet"})
            continue
        item = {"id": post_id, "title": title, "url": post.get("url", ""), "searchDescription": new_description}
        if not apply:
            item["status"] = "DRY_RUN"
            report["updated"].append(item)
            continue
        try:
            svc.posts().patch(blogId=bid, postId=post_id, body={"searchDescription": new_description}).execute()
            verified = svc.posts().get(blogId=bid, postId=post_id).execute()
            saved = str(verified.get("searchDescription", "") or "").strip()
            if saved != new_description:
                raise RuntimeError("Blogger did not persist the requested searchDescription.")
            item["status"] = "UPDATED_VERIFIED"
            report["updated"].append(item)
        except Exception as exc:
            report["errors"].append({**item, "error": str(exc)[:1000]})

    report["updated_count"] = len(report["updated"])
    report["skipped_count"] = len(report["skipped"])
    report["error_count"] = len(report["errors"])
    (out / f"backup-{stamp}.json").write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "latest-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("run_id", "live_posts", "apply_mode", "updated_count", "skipped_count", "error_count")}, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
