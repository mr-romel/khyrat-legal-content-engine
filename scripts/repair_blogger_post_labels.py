from __future__ import annotations

import json
import os
from pathlib import Path

from blogger_publisher import DEFAULT_BLOG_URL, blog_id, normalize_blogger_labels, service


def main() -> int:
    post_id = os.getenv("BLOGGER_LABEL_REPAIR_POST_ID", "").strip()
    if not post_id:
        raise RuntimeError("BLOGGER_LABEL_REPAIR_POST_ID is required.")
    raw = os.getenv("BLOGGER_LABEL_REPAIR_LABELS", '["قانون مصر","الحضانات","ترخيص الحضانة"]')
    requested = json.loads(raw)
    svc = service()
    bid = blog_id(svc, os.getenv("BLOGGER_URL", DEFAULT_BLOG_URL).strip())
    post = svc.posts().get(blogId=bid, postId=post_id).execute()
    existing = post.get("labels") or []
    labels = normalize_blogger_labels([*existing, *requested], max_total_bytes=180, max_labels=8)
    svc.posts().patch(blogId=bid, postId=post_id, body={"labels": labels}).execute()
    verified = svc.posts().get(blogId=bid, postId=post_id).execute()
    saved = verified.get("labels") or []
    report = {
        "post_id": post_id,
        "title": verified.get("title", ""),
        "url": verified.get("url", ""),
        "requested_labels": requested,
        "saved_labels": saved,
        "utf8_bytes": sum(len(label.encode("utf-8")) for label in saved) + max(0, len(saved) - 1),
        "verified": saved == labels,
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/blogger-label-repair.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
