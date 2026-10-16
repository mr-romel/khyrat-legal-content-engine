from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser

from blogger_publisher import DEFAULT_BLOG_URL, blog_id, service


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def canonical_body(html: str) -> str:
    parser = VisibleText()
    parser.feed(html or "")
    text = " ".join(" ".join(parser.parts).split())
    # Ignore invisible formatting differences only; do not use fuzzy similarity.
    return text.strip()


def main() -> int:
    svc = service()
    bid = blog_id(svc, __import__("os").getenv("BLOGGER_URL", DEFAULT_BLOG_URL).strip())
    posts = []
    page = None
    while True:
        args = dict(blogId=bid, status="LIVE", fetchBodies=True, maxResults=500, orderBy="PUBLISHED")
        if page:
            args["pageToken"] = page
        batch = svc.posts().list(**args).execute()
        posts.extend(batch.get("items") or [])
        page = batch.get("nextPageToken")
        if not page:
            break

    groups = {}
    skipped_short = 0
    for post in posts:
        body = canonical_body(str(post.get("content") or ""))
        # Short bodies are too risky to classify as duplicates.
        if len(body) < 500:
            skipped_short += 1
            continue
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        groups.setdefault(digest, []).append(post)

    duplicate_groups = [(digest, items) for digest, items in groups.items() if len(items) > 1]
    print(f"LIVE_POSTS={len(posts)} EXACT_DUPLICATE_GROUPS={len(duplicate_groups)} SHORT_OR_EMPTY_SKIPPED={skipped_short}")
    deleted = 0
    audit = []
    for digest, items in duplicate_groups:
        # Keep the earliest published copy; deterministic tie-breaker by numeric ID.
        items.sort(key=lambda p: (str(p.get("published") or ""), str(p.get("id") or "")))
        keeper = items[0]
        print(f"KEEP id={keeper.get('id')} title={keeper.get('title')}")
        for duplicate in items[1:]:
            # Re-fetch before deletion and re-check exact canonical content to avoid stale-list mistakes.
            fresh = svc.posts().get(blogId=bid, postId=str(duplicate["id"]), fetchBody=True).execute()
            fresh_body = canonical_body(str(fresh.get("content") or ""))
            if fresh_body != canonical_body(str(keeper.get("content") or "")):
                print(f"SKIP_CHANGED id={duplicate.get('id')} title={duplicate.get('title')}")
                continue
            svc.posts().delete(blogId=bid, postId=str(duplicate["id"])).execute()
            deleted += 1
            audit.append({
                "deleted_id": str(duplicate.get("id")),
                "deleted_title": str(duplicate.get("title") or ""),
                "kept_id": str(keeper.get("id")),
                "kept_title": str(keeper.get("title") or ""),
                "body_sha256": digest,
            })
            print(f"DELETED_EXACT_DUPLICATE id={duplicate.get('id')} kept={keeper.get('id')} sha256={digest}")
    print(json.dumps({"deleted_exact_duplicates": deleted, "groups": len(duplicate_groups), "audit": audit}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
