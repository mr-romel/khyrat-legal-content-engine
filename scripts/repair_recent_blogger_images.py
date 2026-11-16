from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from blogger_publisher import DEFAULT_BLOG_URL, blog_id, service, upload_blogger_image
from image_generator import create_legal_image

OUT = Path("artifacts/blogger-recent-image-repair")


def _scene_query(title: str) -> str:
    value = str(title or "")
    mappings = [
        (("نقل الموظف", "جزاء تأديبي", "العمل"), "office paperwork"),
        (("السياسية", "العقود", "الالتزامات"), "business contract"),
        (("التحفظ على المضبوطات", "محضر الضبط"), "customs warehouse"),
        (("الجمارك", "المستوردين", "الاستيراد"), "shipping containers"),
        (("حظر الاستيراد", "السلع"), "import goods"),
        (("ميعاد دعوى", "إلغاء القرار الإداري"), "calendar documents"),
        (("الحزام الأخضر", "تخطيط الأراضي"), "urban planning"),
        (("ترخيص شركة", "استثمار رياضي"), "sports business"),
    ]
    for terms, query in mappings:
        if any(term in value for term in terms):
            return query
    return "Egypt legal administration business contract documents office evidence"


def _replace_hero(content: str, new_url: str, title: str) -> str:
    image = f'<img src="{new_url}" alt="{title}" title="{title}" loading="eager" decoding="async" style="width:100%;height:auto;border-radius:12px">'
    figure = f'<figure>{image}</figure>'
    pattern = re.compile(r'<figure\b[^>]*>\s*<img\b[^>]*>\s*</figure>', re.I | re.S)
    if pattern.search(content):
        return pattern.sub(figure, content, count=1)
    img = re.compile(r'<img\b[^>]*>', re.I | re.S)
    if img.search(content):
        return img.sub(image, content, count=1)
    return figure + content


def main() -> int:
    limit = max(1, min(10, int(os.getenv("BLOGGER_RECENT_IMAGE_REPAIR_LIMIT", "6"))))
    api = service()
    bid = blog_id(api, os.getenv("BLOGGER_URL", DEFAULT_BLOG_URL).strip())
    posts = []
    token = None
    while True:
        args = {"blogId": bid, "status": "LIVE", "fetchBodies": True, "maxResults": 500, "orderBy": "PUBLISHED"}
        if token:
            args["pageToken"] = token
        batch = api.posts().list(**args).execute()
        posts.extend(batch.get("items") or [])
        token = batch.get("nextPageToken")
        if not token:
            break
    posts.sort(key=lambda p: str(p.get("published", "")), reverse=True)
    targets = posts[:limit]
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup, report = [], {"run_id": stamp, "requested": limit, "selected": len(targets), "updated": [], "errors": []}
    hashes: set[str] = set()
    for index, post in enumerate(targets, start=1):
        post_id, title = str(post.get("id", "")).strip(), str(post.get("title", "")).strip()
        url, content = str(post.get("url", "")).strip(), str(post.get("content", "") or "")
        if not post_id or not title or not content:
            report["errors"].append({"post_id": post_id, "title": title, "url": url, "error": "Missing required Blogger fields"})
            continue
        backup.append({"post_id": post_id, "title": title, "url": url, "content": content, "published": post.get("published", "")})
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", post_id)
        path = OUT / f"{index:02d}-{safe_id}.jpg"
        try:
            create_legal_image(
                topic=title,
                image_brief=f"Distinct editorial cover image for this exact legal subject: {title}. Use a unique visual composition, different objects and scene from other recent covers. No generic repeated stock portrait.",
                visual_description=_scene_query(title),
                post_context=content[:5000], output_path=str(path),
                api_key=os.getenv("GEMINI_API_KEY", "").strip(),
                cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip(),
                cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN", "").strip(),
            )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in hashes:
                raise RuntimeError("DUPLICATE_GENERATED_IMAGE_HASH")
            hashes.add(digest)
            hosted = upload_blogger_image(str(path))
            updated = _replace_hero(content, hosted, title)
            if updated == content or hosted not in updated:
                raise RuntimeError("HERO_IMAGE_REPLACEMENT_NOT_VERIFIABLE")
            api.posts().patch(blogId=bid, postId=post_id, body={"content": updated}).execute()
            verified = api.posts().get(blogId=bid, postId=post_id).execute()
            if hosted not in str(verified.get("content", "") or ""):
                raise RuntimeError("BLOGGER_READ_AFTER_WRITE_VERIFICATION_FAILED")
            report["updated"].append({"post_id": post_id, "title": title, "url": url, "published": post.get("published", ""), "image_url": hosted, "sha256": digest, "bytes": path.stat().st_size, "status": "VERIFIED"})
            print(f"VERIFIED_RECENT_IMAGE_REPAIR index={index} post_id={post_id} title={title!r} sha256={digest}")
        except Exception as exc:
            report["errors"].append({"post_id": post_id, "title": title, "url": url, "error": str(exc)[:1200]})
            print(f"RECENT_IMAGE_REPAIR_FAILED post_id={post_id}: {exc}")
    report["updated_count"], report["error_count"] = len(report["updated"]), len(report["errors"])
    (OUT / f"backup-{stamp}.json").write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "latest-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"selected": len(targets), "verified_updated": report["updated_count"], "errors": report["error_count"]}, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
