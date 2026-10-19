from __future__ import annotations

import hashlib
import html
import io
import os
import re
import requests
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from blogger_editor import prepare_article
from blogger_publisher import (
    _clean,
    _related,
    _fallback_article,
    blog_id as resolve_blog_id,
    build_article_html,
    service as blogger_service,
    upload_blogger_image,
)
from config import load_blogger_config
from sheets import create_service as sheets_service, get_values, row_to_dict


BLOGGER_REPAIR_IMAGE_DIR = Path("generated/blogger-repair")
MIN_BODY_CHARS = int(os.getenv("BLOGGER_REPAIR_MIN_BODY_CHARS", "180"))


def _plain(value: str) -> str:
    value = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", str(value or ""))
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return html.unescape(" ".join(value.split())).strip()


def _is_title_only(post: dict[str, Any]) -> bool:
    title = _plain(str(post.get("title", "")))
    content = str(post.get("content", "") or "")
    body_text = _plain(content)
    # Ignore schema/byline/footer noise; only a real editorial body counts.
    editorial_text = re.sub(r"(?i)اسأل محمود|محمود خيرت|محتاج تعرف موقفك القانوني|للتواصل المباشر|واتساب|لينكدإن|فيسبوك", " ", body_text)
    editorial_text = " ".join(editorial_text.split())
    has_image = bool(re.search(r"<img\b", content, re.I))
    # Treat empty content, a title echoed as a paragraph, or a very short body
    # as broken. Existing substantive posts are never overwritten.
    if len(editorial_text) < MIN_BODY_CHARS:
        return True
    if title and editorial_text.casefold() in {title.casefold(), (title + " " + title).casefold()}:
        return True
    return False


def _row_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = _clean(row.get(key, ""))
        if value:
            return value
    return ""


def _load_sheet_rows(config: dict[str, Any]) -> list[dict[str, str]]:
    try:
        svc = sheets_service(config["service_account_info"])
        sheet_range = config["sheet_range"]
        sheet_name = sheet_range.split("!", 1)[0]
        values = get_values(svc, config["sheet_id"], sheet_range)
        if not values:
            return []
        return [row_to_dict(row) for row in values[1:]]
    except Exception as exc:
        print(f"Repair source sheet unavailable; article generation will use post titles only: {exc}")
        return []


def _match_source(post: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, str]:
    pid = str(post.get("id", "")).strip()
    url = str(post.get("url", "")).strip()
    title = _plain(str(post.get("title", ""))).casefold()
    for row in rows:
        row_pid = _row_value(row, "Blogger Post ID", "Post ID")
        row_url = _row_value(row, "Blogger URL", "رابط بلوجر", "رابط المقال")
        row_title = _plain(_row_value(row, "عنوان المقال", "عنوان", "العنوان", "Blogger Title", "title")).casefold()
        if (row_pid and row_pid == pid) or (row_url and url and row_url.rstrip("/") == url.rstrip("/")):
            return row
        if row_title and row_title == title:
            return row
    return {}


def _create_illustration(title: str, path: Path) -> None:
    """Create a locally rendered, title-specific legal illustration without external assets."""
    digest = hashlib.sha256(title.encode("utf-8")).digest()
    palettes = [
        ((17, 31, 56), (36, 83, 119), (222, 185, 105)),
        ((28, 39, 54), (64, 92, 102), (219, 196, 142)),
        ((29, 34, 61), (79, 71, 116), (228, 191, 111)),
        ((22, 46, 48), (47, 103, 91), (220, 191, 125)),
    ]
    bg, panel, gold = palettes[digest[0] % len(palettes)]
    w, h = 1200, 675
    image = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(image)
    # Subtle geometric backdrop.
    for i in range(10):
        x = (digest[(i + 1) % len(digest)] * 5 + i * 137) % w
        y = (digest[(i + 7) % len(digest)] * 2 + i * 71) % h
        r = 28 + (digest[(i + 13) % len(digest)] % 65)
        draw.ellipse((x-r, y-r, x+r, y+r), outline=panel, width=3)
    draw.rounded_rectangle((300, 80, 900, 595), radius=36, fill=panel, outline=gold, width=4)
    # Stylized scales of justice.
    cx, top = 600, 170
    draw.line((cx, top, cx, 475), fill=gold, width=15)
    draw.ellipse((cx-27, top-27, cx+27, top+27), fill=gold)
    draw.line((cx-205, top+75, cx+205, top+75), fill=gold, width=12)
    draw.line((cx-145, top+75, cx-195, top+205), fill=gold, width=7)
    draw.line((cx-145, top+75, cx-95, top+205), fill=gold, width=7)
    draw.arc((cx-230, top+160, cx-60, top+250), 0, 180, fill=gold, width=10)
    draw.line((cx+145, top+75, cx+95, top+205), fill=gold, width=7)
    draw.line((cx+145, top+75, cx+195, top+205), fill=gold, width=7)
    draw.arc((cx+60, top+160, cx+230, top+250), 0, 180, fill=gold, width=10)
    draw.line((cx-125, 480, cx+125, 480), fill=gold, width=14)
    draw.rounded_rectangle((cx-180, 500, cx+180, 530), radius=8, fill=gold)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=90, optimize=True)


def _image_for_post(post: dict[str, Any], row: dict[str, str], svc, bid: str) -> str:
    content = str(post.get("content", "") or "")
    found = re.search(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\']', content, re.I)
    if found and found.group(1).startswith("https://"):
        return found.group(1)
    source_url = _row_value(row, "رابط الصورة", "Image URL", "Image", "الصورة", "رابط الصورة الأصلية")
    if source_url.startswith("https://"):
        try:
            import requests
            response = requests.get(source_url, timeout=40, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            if len(response.content) > 2048:
                path = BLOGGER_REPAIR_IMAGE_DIR / (str(post["id"]) + "-source.jpg")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(response.content)
                return upload_blogger_image(str(path))
        except Exception as exc:
            print(f"Existing source image could not be reused for post {post.get('id')}: {exc}")
    path = BLOGGER_REPAIR_IMAGE_DIR / (str(post["id"]) + "-legal.jpg")
    _create_illustration(str(post.get("title", "مقال قانوني")), path)
    return upload_blogger_image(str(path))


def main() -> int:
    config = load_blogger_config()
    if not config["enabled"]:
        raise RuntimeError("BLOGGER_ENABLED is false; refusing to run repair.")
    svc = blogger_service()
    bid = _clean(config.get("blogger_blog_id", "")) or resolve_blog_id(svc, config["blogger_url"])
    source_rows = _load_sheet_rows(config)

    # The Blogger REST posts.list endpoint returns HTTP 400 in this account.
    # The public JSON feed already exposes LIVE post IDs, titles and bodies, so
    # use it as the inventory and reserve authenticated REST calls for exact-ID
    # patches. This avoids a failed list call blocking all repairs.
    posts: list[dict[str, Any]] = []
    feed_url = config["blogger_url"].rstrip("/") + "/feeds/posts/default"
    try:
        response = requests.get(
            feed_url,
            params={"alt": "json", "max-results": "500"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; KhyratBloggerRepair/1.0)"},
            timeout=45,
        )
        response.raise_for_status()
        entries = response.json().get("feed", {}).get("entry", []) or []
        for entry in entries:
            raw_id = str((entry.get("id") or {}).get("$t", "") or "")
            match = re.search(r"(?:post-|\\.post-)(\\d+)$", raw_id)
            post_id = match.group(1) if match else ""
            title = _clean(str((entry.get("title") or {}).get("$t", "") or ""))
            content = str((entry.get("content") or {}).get("$t", "") or "")
            url = next(
                (str(link.get("href", "")).strip() for link in entry.get("link", []) or []
                 if link.get("rel") == "alternate" and str(link.get("href", "")).startswith("http")),
                "",
            )
            if post_id and title:
                posts.append({"id": post_id, "title": title, "content": content, "url": url, "status": ["LIVE"]})
        print(f"Blogger public-feed inventory loaded: live_posts={len(posts)}")
    except Exception as feed_exc:
        print(f"Blogger public-feed inventory failed; falling back to REST list: {feed_exc}")
        token = None
        while True:
            args: dict[str, Any] = {"blogId": bid, "maxResults": 100, "fetchBodies": True, "status": ["LIVE"]}
            if token:
                args["pageToken"] = token
            result = svc.posts().list(**args).execute()
            posts.extend(result.get("items", []) or [])
            token = result.get("nextPageToken")
            if not token:
                break

    candidates = [p for p in posts if p.get("id") and p.get("title") and _is_title_only(p)]
    max_posts = max(1, int(os.getenv("BLOGGER_REPAIR_MAX_POSTS", "100")))
    candidates = candidates[:max_posts]
    print(f"Blogger title-only repair scan: live_posts={len(posts)} candidates={len(candidates)} max={max_posts}")
    repaired = 0
    failed = 0

    for index, post in enumerate(candidates, start=1):
        pid = str(post["id"])
        title = _clean(str(post.get("title", "")))
        row = _match_source(post, source_rows)
        topic = _row_value(row, "الموضوع", "Topic", "عنوان المقال", "عنوان", "العنوان") or title
        original_post = _row_value(row, "المحتوى", "Content", "Post", "نص المنشور", "النص")
        legal_sources = _row_value(row, "المصادر القانونية", "Legal Sources", "المصادر")
        editorial_input = original_post or (
            f"المطلوب مقال توعوي عام بعنوان: {title}. اشرح المبادئ العامة وخطوات التحقق من الوقائع والمستندات، "
            "ولا تذكر أرقام مواد أو مواعيد أو عقوبات أو أحكام قضائية ما لم تكن موجودة صراحة في المصادر المقدمة."
        )
        print(f"[{index}/{len(candidates)}] Repairing post id={pid} title={title!r}")
        try:
            article = None
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            if api_key:
                try:
                    article = prepare_article(
                        api_key=api_key,
                        model=os.getenv("GEMINI_MODEL", "").strip() or os.getenv("GEMINI_FALLBACK_MODEL", "").strip() or "gemini-3.6-flash",
                        topic=topic,
                        post=editorial_input,
                        legal_sources=legal_sources,
                    )
                    print(f"Editorial article generated for post {pid}.")
                except Exception as generation_exc:
                    # A free-tier quota/rate limit must not leave existing live posts title-only.
                    # Use the project's deterministic structured article builder as a no-API fallback.
                    print(f"AI article generation unavailable for post {pid}; using local structured fallback: {str(generation_exc)[:500]}")
            if not isinstance(article, dict):
                article = _fallback_article(topic, editorial_input, legal_sources)
            # Preserve the existing public title and permalink; replace only the broken body.
            article["title"] = title
            image_url = _image_for_post(post, row, svc, bid)
            related = _related(svc, bid, topic)
            new_content = build_article_html(
                title=title,
                topic=topic,
                post=editorial_input,
                image_url=image_url,
                legal_sources=legal_sources,
                related=related,
                article=article,
            )
            visible = _plain(new_content)
            if len(visible) < MIN_BODY_CHARS or not re.search(r"<img\b", new_content, re.I):
                raise RuntimeError("Generated replacement failed body/image validation.")
            updated = svc.posts().patch(
                blogId=bid,
                postId=pid,
                body={"content": new_content},
                fetchBody=True,
            ).execute()
            verified = str(updated.get("content", "") or "")
            if len(_plain(verified)) < MIN_BODY_CHARS or not re.search(r"<img\b", verified, re.I):
                raise RuntimeError("Blogger API returned an update without a verified body and image.")
            repaired += 1
            print(f"REPAIRED post_id={pid} url={updated.get('url','')} body_chars={len(_plain(verified))} image=present")
        except Exception as exc:
            failed += 1
            print(f"REPAIR_FAILED post_id={pid} title={title!r}: {str(exc)[:1200]}")

    print(f"Blogger title-only repair complete: candidates={len(candidates)} repaired={repaired} failed={failed}")
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
