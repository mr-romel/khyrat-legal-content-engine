from __future__ import annotations

import html
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from blogger_publisher import DEFAULT_BLOG_URL, blog_id, service

BACKUP_DIR = Path(os.getenv("BLOGGER_LINK_BACKUP_DIR", "artifacts/blogger-internal-links/backups"))
REPORT_DIR = Path(os.getenv("BLOGGER_LINK_REPORT_DIR", "artifacts/blogger-internal-links"))
STOPWORDS = {
    "في", "من", "على", "عن", "الى", "إلى", "ما", "هل", "كيف", "متى", "مع",
    "هذا", "هذه", "ذلك", "تلك", "التي", "الذي", "و", "او", "أو", "ثم",
    "الذي", "التي", "التى", "بين", "بعد", "قبل", "عند", "كل", "او", "وقد",
    "قانون", "القانون", "مصر", "المصري", "المصرية", "دليل", "شرح", "كيفية",
}


def norm(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    value = re.sub(r"[إأآٱ]", "ا", value).replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", value).strip()


def terms(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9\u0600-\u06ff]+", norm(text))
            if len(x) > 2 and x not in STOPWORDS}


def choose_related(source: dict, posts: list[dict], max_links: int = 2) -> list[dict]:
    source_terms = terms(source.get("title", ""))
    existing_html = str(source.get("content", "") or "")
    existing_urls = set(re.findall(r'''href\s*=\s*["']([^"']+)["']''', existing_html, flags=re.I))
    candidates = []
    for target in posts:
        if str(target.get("id")) == str(source.get("id")):
            continue
        url = str(target.get("url", "")).strip()
        title = str(target.get("title", "")).strip()
        if not url or not title or url in existing_urls:
            continue
        overlap = source_terms & terms(title)
        # Conservative relevance gate: at least two non-generic title terms.
        if len(overlap) < 2:
            continue
        candidates.append((len(overlap), title, url, sorted(overlap)))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return [{"title": title, "url": url, "shared_terms": shared}
            for _, title, url, shared in candidates[:max_links]]


def add_related_section(content: str, related: list[dict]) -> str:
    content = str(content or "")
    if not related:
        return content
    # Idempotent: never append a second related-links section.
    if re.search(r"(?:اقرأ\s+أيضًا|مقالات\s+ذات\s+صلة|related\s+articles)", content, re.I):
        return content
    items = "".join(
        f'<li><a href="{html.escape(item["url"], quote=True)}">{html.escape(item["title"])}</a></li>'
        for item in related
    )
    section = '<section class="khyrat-related-articles"><h2>اقرأ أيضًا</h2><ul>' + items + "</ul></section>"
    if re.search(r"</article\s*>\s*$", content, re.I):
        return re.sub(r"</article\s*>\s*$", section + "</article>", content, flags=re.I)
    return content.rstrip() + section


def main() -> int:
    apply = os.getenv("BLOGGER_LINK_APPLY", "false").strip().lower() in {"1", "true", "yes"}
    limit = max(1, min(500, int(os.getenv("BLOGGER_LINK_LIMIT", "500"))))
    blog_url = os.getenv("BLOGGER_URL", DEFAULT_BLOG_URL).strip()
    svc = service()
    bid = blog_id(svc, blog_url)
    batch = svc.posts().list(blogId=bid, status="LIVE", fetchBodies=True, maxResults=500, orderBy="PUBLISHED").execute()
    posts = list(batch.get("items") or [])
    token = batch.get("nextPageToken")
    while token:
        batch = svc.posts().list(blogId=bid, status="LIVE", fetchBodies=True, maxResults=500, orderBy="PUBLISHED", pageToken=token).execute()
        posts.extend(batch.get("items") or [])
        token = batch.get("nextPageToken")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = BACKUP_DIR / f"blogger-posts-before-{run_id}.json"
    backup = [{"id": str(p.get("id", "")), "title": p.get("title", ""), "url": p.get("url", ""),
               "updated": p.get("updated", ""), "content": p.get("content", "")} for p in posts]
    backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "run_id": run_id, "blog_url": blog_url, "live_posts": len(posts),
        "apply_mode": apply, "backup_file": str(backup_path),
        "updated": [], "skipped": [], "errors": [],
        "safety": "Only appends a maximum of two links to already published posts, requires at least two meaningful shared title terms, preserves original HTML in the backup, skips posts already having a related section, and changes no titles/body text.",
    }
    for post in posts[:limit]:
        post_id = str(post.get("id", "")).strip()
        title = str(post.get("title", "")).strip()
        content = str(post.get("content", "") or "")
        if not post_id or not title or not content:
            report["skipped"].append({"id": post_id, "title": title, "reason": "missing id/title/content"})
            continue
        if re.search(r"(?:اقرأ\s+أيضًا|مقالات\s+ذات\s+صلة|related\s+articles)", content, re.I):
            report["skipped"].append({"id": post_id, "title": title, "reason": "related section already exists"})
            continue
        related = choose_related(post, posts)
        if not related:
            report["skipped"].append({"id": post_id, "title": title, "reason": "no sufficiently related target"})
            continue
        updated_content = add_related_section(content, related)
        if updated_content == content:
            report["skipped"].append({"id": post_id, "title": title, "reason": "no safe change generated"})
            continue
        item = {"id": post_id, "title": title, "url": post.get("url", ""), "related": related}
        if apply:
            try:
                svc.posts().patch(blogId=bid, postId=post_id, body={"content": updated_content}).execute()
                item["status"] = "UPDATED"
                report["updated"].append(item)
                print(f"UPDATED post={post_id} title={title!r} links={len(related)}")
            except Exception as exc:
                report["errors"].append({**item, "error": str(exc)[:1200]})
                print(f"ERROR post={post_id}: {exc}")
        else:
            item["status"] = "DRY_RUN"
            report["updated"].append(item)

    report["updated_count"] = len(report["updated"])
    report["skipped_count"] = len(report["skipped"])
    report["error_count"] = len(report["errors"])
    report_path = REPORT_DIR / f"internal-link-apply-report-{run_id}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_DIR / "latest-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("run_id", "live_posts", "apply_mode", "updated_count", "skipped_count", "error_count", "backup_file", "report_file")}, ensure_ascii=False))
    print(f"REPORT_FILE={report_path}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
