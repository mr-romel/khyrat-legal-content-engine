from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from blogger_publisher import DEFAULT_BLOG_URL, blog_id, service
from blogger_seo_audit import run as run_public_audit
from blogger_ui_publisher import set_search_description_ui


def _plain_text(value: str) -> str:
    value = re.sub(r"<(script|style)\\b[^>]*>.*?</\\1>", " ", str(value or ""), flags=re.I | re.S)
    value = re.sub(r"<br\\s*/?>|</p\\s*>|</li\\s*>|</h[1-6]\\s*>", ". ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\\s+", " ", value).strip(" .\\t\\r\\n")


def _first_paragraph(fragment: str) -> str:
    match = re.search(r"<p\\b[^>]*>(.*?)</p\\s*>", fragment, flags=re.I | re.S)
    return _plain_text(match.group(1) if match else fragment)


def build_search_description(content: str, title: str = "") -> str:
    """Derive a truthful snippet from the article's own concise answer or opening paragraph."""
    content = str(content or "")
    answer = re.search(
        r"<h[2-4]\\b[^>]*>[^<]*(?:الإجابة المختصرة|ملخص الإجابة|الخلاصة)[^<]*</h[2-4]\\s*>(.*?)(?=<h[1-4]\\b|$)",
        content,
        flags=re.I | re.S,
    )
    candidate = _first_paragraph(answer.group(1)) if answer else ""
    if len(candidate) < 70:
        candidate = _first_paragraph(content)
    candidate = re.sub(r"^" + re.escape(str(title or "").strip()) + r"\\s*[:：—-]?\\s*", "", candidate, flags=re.I)
    candidate = re.sub(r"\\s+", " ", candidate).strip()
    if len(candidate) <= 150:
        return candidate
    cut = candidate[:150]
    boundary = cut.rfind(" ")
    if boundary >= 115:
        cut = cut[:boundary]
    return cut.rstrip(" ،؛:—-") + "…"


def _url_key(value: str) -> str:
    return str(value or "").split("#", 1)[0].split("?", 1)[0].rstrip("/").casefold()


def main() -> int:
    apply = os.getenv("BLOGGER_SEARCH_DESCRIPTION_APPLY", "false").strip().lower() in {"1", "true", "yes"}
    limit = max(1, min(500, int(os.getenv("BLOGGER_SEARCH_DESCRIPTION_LIMIT", "500"))))
    blog_url = os.getenv("BLOGGER_URL", DEFAULT_BLOG_URL).strip()
    if not os.getenv("BLOGGER_UI_STORAGE_STATE_B64", "").strip():
        raise RuntimeError("BLOGGER_UI_STORAGE_STATE_B64 is required for Blogger editor Search description updates.")

    out = Path("artifacts/blogger-search-descriptions")
    out.mkdir(parents=True, exist_ok=True)
    audit_dir = Path("artifacts/seo-audit")
    initial_audit = run_public_audit(str(audit_dir))
    missing_urls = {
        _url_key(item.get("url", ""))
        for item in initial_audit.get("article_pages", [])
        if item.get("url") and not str(item.get("meta_description", "")).strip()
    }
    if not missing_urls:
        print("Public audit found no missing Search descriptions in the audited article set.")
        return 0

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

    targets = [p for p in posts if _url_key(p.get("url", "")) in missing_urls][:limit]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = []
    report = {
        "run_id": stamp, "blog_url": blog_url, "live_posts": len(posts),
        "audited_missing_descriptions": len(missing_urls), "matched_posts": len(targets),
        "apply_mode": apply, "updated": [], "skipped": [], "errors": [],
    }

    for post in targets:
        post_id = str(post.get("id", "")).strip()
        title = str(post.get("title", "")).strip()
        content = str(post.get("content", "") or "")
        description = build_search_description(content, title)
        backup.append({
            "id": post_id, "title": title, "url": post.get("url", ""),
            "old_public_meta_description": "", "proposed_search_description": description,
        })
        if len(description) < 70:
            report["skipped"].append({"id": post_id, "title": title, "reason": "insufficient grounded text"})
            continue
        item = {"id": post_id, "title": title, "url": post.get("url", ""), "search_description": description}
        if not apply:
            item["status"] = "DRY_RUN"
            report["updated"].append(item)
            continue
        try:
            status = set_search_description_ui(
                blog_id=bid, post_id=post_id, search_description=description
            )
            item["status"] = status
            report["updated"].append(item)
        except Exception as exc:
            report["errors"].append({**item, "error": str(exc)[:1200]})

    report["updated_count"] = len(report["updated"])
    report["skipped_count"] = len(report["skipped"])
    report["error_count"] = len(report["errors"])
    (out / f"backup-{stamp}.json").write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "latest-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if apply and report["updated"]:
        verified_audit = run_public_audit(str(audit_dir))
        report["verification"] = verified_audit.get("summary", {})
        report["verification_missing_meta_descriptions"] = report["verification"].get("articles_missing_meta_description")
        (out / "latest-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "run_id": stamp, "live_posts": len(posts), "audited_missing_descriptions": len(missing_urls),
        "matched_posts": len(targets), "apply_mode": apply, "updated_count": report["updated_count"],
        "skipped_count": report["skipped_count"], "error_count": report["error_count"],
        "verification_missing_meta_descriptions": report.get("verification_missing_meta_descriptions"),
    }, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
