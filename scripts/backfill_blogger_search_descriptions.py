from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from blogger_publisher import DEFAULT_BLOG_URL, blog_id, service
from blogger_seo_audit import run as run_public_audit
from config import load_blogger_config
from sheets import append_row, create_service, ensure_headers, get_values, row_to_dict, update_row


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


def _url_key(value: str) -> str:
    return str(value or "").split("#", 1)[0].split("?", 1)[0].rstrip("/").casefold()


def main() -> int:
    apply = os.getenv("BLOGGER_SEARCH_DESCRIPTION_APPLY", "false").strip().lower() in {"1", "true", "yes"}
    limit = max(1, min(500, int(os.getenv("BLOGGER_SEARCH_DESCRIPTION_LIMIT", "500"))))
    blog_url = os.getenv("BLOGGER_URL", DEFAULT_BLOG_URL).strip()
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

    config = load_blogger_config()
    sheet_service = create_service(config["service_account_info"])
    sheet_name = config["sheet_range"].split("!", 1)[0]
    ensure_headers(sheet_service, config["sheet_id"], sheet_name)
    sheet_values = get_values(sheet_service, config["sheet_id"], config["sheet_range"])
    if not sheet_values:
        raise RuntimeError("Blogger content sheet is empty; cannot safely map live posts to rows.")
    sheet_rows = [row_to_dict(row) for row in sheet_values[1:]]
    row_by_url = {
        _url_key(row.get("Blogger URL", "")): (row_number, row)
        for row_number, row in enumerate(sheet_rows, start=2)
        if _url_key(row.get("Blogger URL", ""))
    }

    blogger_service = service()
    resolved_blog_id = blog_id(blogger_service, blog_url)
    posts = []
    token = None
    while True:
        args = {"blogId": resolved_blog_id, "status": "LIVE", "fetchBodies": True, "maxResults": 500}
        if token:
            args["pageToken"] = token
        batch = blogger_service.posts().list(**args).execute()
        posts.extend(batch.get("items") or [])
        token = batch.get("nextPageToken")
        if not token:
            break

    targets = [post for post in posts if _url_key(post.get("url", "")) in missing_urls][:limit]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = []
    report = {
        "run_id": stamp, "blog_url": blog_url, "live_posts": len(posts),
        "audited_missing_descriptions": len(missing_urls), "matched_posts": len(targets),
        "apply_mode": apply, "updated": [], "skipped": [], "errors": [],
        "method": "Google Sheet staging + existing blogger_seo_worker UI editor + public-page verification",
    }

    for post in targets:
        post_id = str(post.get("id", "")).strip()
        title = str(post.get("title", "")).strip()
        url = str(post.get("url", "")).strip()
        row_match = row_by_url.get(_url_key(url)) or next(
            ((rn, row) for rn, row in row_by_url.values() if str(row.get("Blogger Post ID", "")).strip() == post_id),
            None,
        )
        existing_description = str(row_match[1].get("Blogger Meta Description", "") or "").strip() if row_match else ""
        description = existing_description or build_search_description(str(post.get("content", "") or ""), title)
        if len(description) < 70:
            report["skipped"].append({"id": post_id, "title": title, "url": url, "reason": "insufficient grounded text"})
            continue
        backup.append({
            "id": post_id, "title": title, "url": url,
            "sheet_row": row_match[0] if row_match else None,
            "old_sheet_description": existing_description,
            "proposed_search_description": description,
            "old_seo_status": row_match[1].get("Blogger SEO Status", "") if row_match else "",
        })
        item = {"id": post_id, "title": title, "url": url, "search_description": description}
        if not apply:
            item["status"] = "DRY_RUN"
            report["updated"].append(item)
            continue
        try:
            if row_match:
                row_number, row = row_match
                notes = str(row.get("ملاحظات", "") or "").strip()
                if "LEGACY SEO BACKFILL" not in notes.upper():
                    notes = (notes + " | " if notes else "") + "LEGACY SEO BACKFILL"
                update_row(sheet_service, config["sheet_id"], sheet_name, row_number, {
                    "Blogger Meta Description": description[:150],
                    "Blogger SEO Status": "PENDING",
                    "Blogger SEO Error": "",
                    "ملاحظات": notes,
                })
                item["sheet_row"] = row_number
                item["status"] = "STAGED_EXISTING_ROW"
            else:
                published = str(post.get("published", "") or "")
                date_part = published[:10]
                time_part = published[11:16] if "T" in published else ""
                row_values = {
                    "ID": f"LEGACY-{post_id}",
                    "الموضوع": title,
                    "تاريخ النشر": date_part,
                    "ساعة النشر": time_part,
                    "نوع الجدولة": "LEGACY_SEO_BACKFILL",
                    "الحالة": "PUBLISHED",
                    "المحتوى": str(post.get("content", "") or ""),
                    "ملاحظات": "LEGACY SEO BACKFILL | existing live post; do not republish",
                    "Blogger Status": "PUBLISHED",
                    "Blogger Post ID": post_id,
                    "Blogger URL": url,
                    "Blogger Search Title": title,
                    "Blogger Search Query": title,
                    "Blogger Meta Description": description[:150],
                    "Blogger SEO Status": "PENDING",
                    "Blogger SEO Error": "",
                }
                row_number = append_row(sheet_service, config["sheet_id"], sheet_name, row_values)
                if row_number < 2:
                    raise RuntimeError("Google Sheets did not return a valid appended row number.")
                item["sheet_row"] = row_number
                item["status"] = "APPENDED_LEGACY_ROW"
                row_by_url[_url_key(url)] = (row_number, row_values)
            report["updated"].append(item)
        except Exception as exc:
            report["errors"].append({**item, "error": str(exc)[:1200]})

    report["updated_count"] = len(report["updated"])
    report["skipped_count"] = len(report["skipped"])
    report["error_count"] = len(report["errors"])
    (out / f"backup-{stamp}.json").write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "latest-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if apply and report["updated"]:
        batch_size = max(1, min(10, int(os.getenv("BLOGGER_SEARCH_DESCRIPTION_BATCH_SIZE", "5"))))
        os.environ["BLOGGER_SEO_MAX_POSTS"] = str(batch_size)
        from blogger_seo_worker import main as run_existing_seo_worker
        worker_exit = run_existing_seo_worker()
        values_after = get_values(sheet_service, config["sheet_id"], config["sheet_range"])
        rows_after = [row_to_dict(row) for row in values_after[1:]] if values_after else []
        status_by_url = {
            _url_key(row.get("Blogger URL", "")): {
                "status": row.get("Blogger SEO Status", ""),
                "error": row.get("Blogger SEO Error", ""),
            }
            for row in rows_after
        }
        for item in report["updated"]:
            item["worker_result"] = status_by_url.get(_url_key(item["url"]), {})
            item["status"] = item["worker_result"].get("status", "UNKNOWN")
        report["worker_exit_code"] = worker_exit
        report["verified_count"] = sum(1 for item in report["updated"] if str(item["status"]).upper() == "VERIFIED")
        report["failed_count"] = sum(1 for item in report["updated"] if str(item["status"]).upper() == "FAILED")
        verified_audit = run_public_audit(str(audit_dir))
        report["verification"] = verified_audit.get("summary", {})
        report["verification_missing_meta_descriptions"] = report["verification"].get("articles_missing_meta_description")
        (out / "latest-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "run_id": stamp, "live_posts": len(posts), "audited_missing_descriptions": len(missing_urls),
        "matched_posts": len(targets), "apply_mode": apply, "updated_count": report["updated_count"],
        "skipped_count": report["skipped_count"], "error_count": report["error_count"],
        "verified_count": report.get("verified_count", 0),
        "failed_count": report.get("failed_count", 0),
        "verification_missing_meta_descriptions": report.get("verification_missing_meta_descriptions"),
    }, ensure_ascii=False))
    return 1 if report["errors"] or report.get("failed_count", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
