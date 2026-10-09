from __future__ import annotations

import os
import re
import time
from html import unescape

import requests

from blogger_site_setup import PAGES
from blogger_ui_publisher import publish_page_ui, resolve_blog_id_ui

BLOG_URL = os.getenv("BLOGGER_URL", "https://askmahmoudkhyrat.blogspot.com/").strip().rstrip("/")
BLOG_ID = os.getenv("BLOGGER_BLOG_ID", "").strip()
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AskMahmoudBloggerPages/1.0)"}


def _clean(value: object) -> str:
    return re.sub(r"\\s+", " ", str(value or "")).strip()


def _public_pages() -> list[dict[str, str]]:
    url = BLOG_URL + "/feeds/pages/default"
    response = requests.get(url, params={"alt": "json", "max-results": "100"}, headers=HEADERS, timeout=25)
    response.raise_for_status()
    payload = response.json()
    feed = payload.get("feed", {})
    entries = feed.get("entry", []) or []
    pages = []
    for entry in entries:
        title = _clean(entry.get("title", {}).get("$t", ""))
        raw_id = _clean(entry.get("id", {}).get("$t", ""))
        match = re.search(r"\\.page-(\\d+)$", raw_id)
        page_id = match.group(1) if match else ""
        content = str(entry.get("content", {}).get("$t", "") or "")
        links = entry.get("link", []) or []
        url = next((str(x.get("href", "")) for x in links if x.get("rel") == "alternate"), "")
        if title:
            pages.append({"title": title, "page_id": page_id, "content": content, "url": url})
    return pages


def main() -> int:
    if os.getenv("BLOGGER_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        print("Blogger disabled; static pages skipped.")
        return 0
    if not os.getenv("BLOGGER_UI_STORAGE_STATE_B64", "").strip():
        raise RuntimeError("BLOGGER_UI_STORAGE_STATE_B64 is required for UI-based Blogger static-page management.")
    blog_id = BLOG_ID or resolve_blog_id_ui()

    # Read the public page feed first so retries update existing pages instead
    # of creating duplicate pages. Fail closed if we cannot inspect current pages.
    current_pages = _public_pages()
    by_title = {item["title"].casefold(): item for item in current_pages}
    for page in PAGES:
        title = _clean(page.get("title", ""))
        content = str(page.get("content", "") or "")
        existing = by_title.get(title.casefold())
        if existing and re.sub(r"\\s+", " ", existing.get("content", "")).strip() == re.sub(r"\\s+", " ", content).strip():
            print(f"Blogger static page already current: {title} -> {existing.get('url', '')}")
            continue
        page_id = existing.get("page_id", "") if existing else ""
        result = publish_page_ui(title=title, content_html=content, blog_id=blog_id, page_id=page_id)
        print(f"Blogger static page {'updated' if page_id else 'published'}: {title}; editor={result.get('editor_url','')}")
        time.sleep(1.0)

    verified = {item["title"].casefold(): item for item in _public_pages()}
    missing = [page["title"] for page in PAGES if page["title"].casefold() not in verified]
    if missing:
        raise RuntimeError("Static-page publication verification failed; pages not found in public Blogger feed: " + ", ".join(missing))
    for page in PAGES:
        item = verified[page["title"].casefold()]
        print(f"Blogger static page verified: {page['title']} -> {item.get('url', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
