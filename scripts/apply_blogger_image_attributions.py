from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from blogger_publisher import DEFAULT_BLOG_URL, blog_id, service

TARGETS = [
    {
        "post_id": "8214385121124394782",
        "credit": "Business contract and power of attorney — Reed, Michael / Morrell, Z.N. — CC BY 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:(Business_contract_and_power_of_attorney)_-_DPLA_-_4b483db22808e799cd02f23316393fef_(page_1).jpg",
        "license": "https://creativecommons.org/licenses/by/4.0",
    },
    {
        "post_id": "6459880917883553270",
        "credit": "Shipping Containers — CGP Grey — CC BY 2.0",
        "source": "https://commons.wikimedia.org/wiki/File:DK-84_-_K%C3%B8benhavn_-_Copenhagen_-_Denmark_-_Shipping_Containers_-_Intermodal_Containers_(4890885214).jpg",
        "license": "https://creativecommons.org/licenses/by/2.0",
    },
]

def add_credit(content: str, item: dict) -> str:
    if "Khyrat image attribution" in content:
        return content
    credit = html.escape(item["credit"])
    source = html.escape(item["source"], quote=True)
    license_url = html.escape(item["license"], quote=True)
    caption = (
        '<figcaption class="khyrat-image-attribution">'
        'مصدر الصورة: <a href="' + source + '" rel="nofollow noopener">' + credit + '</a> · '
        '<a href="' + license_url + '" rel="license nofollow noopener">ترخيص الاستخدام</a>'
        '</figcaption><!-- Khyrat image attribution -->'
    )
    match = re.search(r"<figure\\b[^>]*>.*?</figure>", content, flags=re.I | re.S)
    if match:
        block = match.group(0)
        return content[:match.start()] + re.sub(r"</figure>\\s*$", caption + "</figure>", block, flags=re.I) + content[match.end():]
    return content

def main() -> int:
    api = service()
    bid = blog_id(api, os.getenv("BLOGGER_URL", DEFAULT_BLOG_URL).strip())
    out = Path("artifacts/blogger-image-attribution")
    out.mkdir(parents=True, exist_ok=True)
    report = {"updated": [], "errors": []}
    for item in TARGETS:
        try:
            post = api.posts().get(blogId=bid, postId=item["post_id"]).execute()
            content = str(post.get("content", "") or "")
            backup = {"post_id": item["post_id"], "title": post.get("title", ""), "url": post.get("url", ""), "content": content}
            backup_path = out / (item["post_id"] + "-before.json")
            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
            updated = add_credit(content, item)
            if updated != content:
                api.posts().patch(blogId=bid, postId=item["post_id"], body={"content": updated}).execute()
            verified = api.posts().get(blogId=bid, postId=item["post_id"]).execute()
            if "Khyrat image attribution" not in str(verified.get("content", "")):
                raise RuntimeError("Attribution read-after-write verification failed")
            report["updated"].append({"post_id": item["post_id"], "title": post.get("title", ""), "url": post.get("url", ""), "credit": item["credit"], "status": "VERIFIED"})
            print("VERIFIED_IMAGE_ATTRIBUTION post_id=" + item["post_id"])
        except Exception as exc:
            report["errors"].append({"post_id": item["post_id"], "error": str(exc)[:1000]})
            print("IMAGE_ATTRIBUTION_FAILED post_id=" + item["post_id"] + ": " + str(exc))
    report["updated_count"] = len(report["updated"])
    report["error_count"] = len(report["errors"])
    (out / "latest-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if report["errors"] else 0

if __name__ == "__main__":
    raise SystemExit(main())