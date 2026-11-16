from __future__ import annotations

import os
import re
import time
from html import escape, unescape

import requests

from blogger_site_setup import PAGES
from blogger_publisher import blog_id as resolve_blog_id_api, service as blogger_service
from blogger_ui_publisher import publish_page_ui, resolve_blog_id_ui

BLOG_URL = os.getenv("BLOGGER_URL", "https://askmahmoudkhyrat.blogspot.com/").strip().rstrip("/")
BLOG_ID = os.getenv("BLOGGER_BLOG_ID", "").strip()
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AskMahmoudBloggerPages/1.0)"}

SITE_NAV = '<nav aria-label="روابط الموقع" style="margin:0 0 22px;padding:12px 16px;border:1px solid #ddd;border-radius:10px;display:flex;flex-wrap:wrap;gap:12px"><a href="https://askmahmoudkhyrat.blogspot.com/">الرئيسية</a><a href="https://askmahmoudkhyrat.blogspot.com/p/blog-page_03.html">الهوية الرسمية</a><a href="https://askmahmoudkhyrat.blogspot.com/p/blog-page.html">من نحن</a><a href="https://askmahmoudkhyrat.blogspot.com/p/blog-page_980.html">فهرس الموضوعات</a><a href="https://askmahmoudkhyrat.blogspot.com/p/blog-page_07.html">تواصل معنا</a></nav>'

def _page_content(page):
    content = str(page.get("content", "") or "")
    return content if 'aria-label="روابط الموقع"' in content else SITE_NAV + content

SERVICE_PAGE_TITLES = {
    "الخدمات القانونية للأفراد والشركات",
    "محامي قضايا العمل ومستحقات العامل في مصر",
    "مراجعة وصياغة العقود للشركات والأفراد",
    "الخدمات القانونية للشركات وتأسيسها",
    "قضايا التعويض والمسؤولية المدنية",
}


def build_service_navigation(content: str, current_title: str, pages: list[dict]) -> str:
    """Build reciprocal links from actual Blogger page URLs, never guessed slugs."""
    cleaned = re.sub(
        r"""<nav[^>]*class=["']khyrat-service-links["'][^>]*>[\\s\\S]*?</nav>""",
        "",
        str(content or ""),
        flags=re.I,
    )
    links = []
    current_key = _clean(current_title).casefold()
    for item in pages:
        title = _clean(item.get("title", ""))
        url = _clean(item.get("url", ""))
        if title.casefold() == current_key or title not in SERVICE_PAGE_TITLES or not url.startswith(BLOG_URL):
            continue
        links.append(f'<li><a href="{escape(url, quote=True)}">{escape(title)}</a></li>')
    if not links:
        return cleaned
    navigation = (
        '<nav class="khyrat-service-links" aria-label="الخدمات القانونية ذات الصلة">'
        '<h2>خدمات قانونية ذات صلة</h2><ul>' + "".join(links) + '</ul></nav>'
    )
    return cleaned.rstrip() + navigation




def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


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
        match = re.search(r"\.page-(\d+)$", raw_id)
        page_id = match.group(1) if match else ""
        content = str(entry.get("content", {}).get("$t", "") or "")
        links = entry.get("link", []) or []
        url = next((str(x.get("href", "")) for x in links if x.get("rel") == "alternate"), "")
        if title:
            pages.append({"title": title, "page_id": page_id, "content": content, "url": url})
    return pages



def _publish_pages_via_api() -> bool:
    """Prefer Blogger's authenticated REST API; UI automation is a fallback only."""
    if not os.getenv("BLOGGER_OAUTH_JSON", "").strip():
        return False

    svc = blogger_service()
    target_blog_id = BLOG_ID or resolve_blog_id_api(svc, BLOG_URL)
    existing: dict[str, list[dict]] = {}
    token = None
    while True:
        kwargs = {"blogId": target_blog_id, "maxResults": 100}
        if token:
            kwargs["pageToken"] = token
        data = svc.pages().list(**kwargs).execute()
        for item in data.get("items", []) or []:
            existing.setdefault(_clean(item.get("title", "")).casefold(), []).append(item)
        token = data.get("nextPageToken")
        if not token:
            break

    for page in PAGES:
        title = _clean(page.get("title", ""))
        payload = {"title": title, "content": _page_content(page)}
        matches = existing.get(title.casefold(), [])
        if len(matches) > 1:
            raise RuntimeError(
                f"Duplicate Blogger pages detected for managed title {title!r}: "
                + ", ".join(str(item.get("url", item.get("id", ""))) for item in matches)
                + ". Refusing to publish until duplicates are resolved."
            )
        current = matches[0] if matches else None
        if current and str(current.get("id", "")).strip():
            if str(current.get("content", "") or "") != payload["content"]:
                result = svc.pages().update(
                    blogId=target_blog_id,
                    pageId=str(current["id"]),
                    body={**current, **payload},
                ).execute()
                print(f"Blogger static page updated through REST API: {title}; url={result.get('url', '')}")
            else:
                print(f"Blogger static page already current through REST API: {title}; url={current.get('url', '')}")
        else:
            result = svc.pages().insert(
                blogId=target_blog_id,
                body=payload,
                isDraft=False,
            ).execute()
            print(f"Blogger static page created through REST API: {title}; url={result.get('url', '')}")

    # Verify persistence against Blogger's authenticated source of truth, not
    # only the eventually-consistent public Pages feed.
    verified: dict[str, dict] = {}
    token = None
    while True:
        kwargs = {"blogId": target_blog_id, "maxResults": 100}
        if token:
            kwargs["pageToken"] = token
        data = svc.pages().list(**kwargs).execute()
        for item in data.get("items", []) or []:
            verified[_clean(item.get("title", "")).casefold()] = item
        token = data.get("nextPageToken")
        if not token:
            break

    missing = [
        page["title"] for page in PAGES
        if page["title"].casefold() not in verified
        or not str(verified[page["title"].casefold()].get("url", "")).startswith(BLOG_URL)
    ]
    if missing:
        raise RuntimeError(
            "Blogger REST API publication verification failed; missing pages or public URLs: "
            + ", ".join(missing)
        )
    verified_pages = [
        {"title": str(item.get("title", "")), "url": str(item.get("url", ""))}
        for item in verified.values()
    ]
    for page in PAGES:
        item = verified[page["title"].casefold()]
        if page["title"] in SERVICE_PAGE_TITLES:
            page_id = str(item.get("id", "")).strip()
            updated_content = build_service_navigation(
                str(item.get("content", "") or ""), page["title"], verified_pages
            )
            if page_id and updated_content != str(item.get("content", "") or ""):
                svc.pages().patch(
                    blogId=target_blog_id, pageId=page_id,
                    body={"content": updated_content},
                ).execute()
                print(f"Blogger service cross-links updated: {page['title']}")
        print(f"Blogger static page REST-verified: {page['title']} -> {item.get('url', '')}")
    return True


def main() -> int:
    if os.getenv("BLOGGER_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        print("Blogger disabled; static pages skipped.")
        return 0
    if _publish_pages_via_api():
        return 0
    if not os.getenv("BLOGGER_UI_STORAGE_STATE_B64", "").strip():
        raise RuntimeError("Set BLOGGER_OAUTH_JSON for REST API publication or BLOGGER_UI_STORAGE_STATE_B64 for the UI fallback.")
    blog_id = BLOG_ID or resolve_blog_id_ui()

    # Read the public page feed first so retries update existing pages instead
    # of creating duplicate pages. Fail closed if we cannot inspect current pages.
    current_pages = _public_pages()
    by_title = {item["title"].casefold(): item for item in current_pages}
    for page in PAGES:
        title = _clean(page.get("title", ""))
        content = _page_content(page)
        existing = by_title.get(title.casefold())
        if existing and re.sub(r"\s+", " ", existing.get("content", "")).strip() == re.sub(r"\s+", " ", content).strip():
            print(f"Blogger static page already current: {title} -> {existing.get('url', '')}")
            continue
        page_id = existing.get("page_id", "") if existing else ""
        result = publish_page_ui(title=title, content_html=content, blog_id=blog_id, page_id=page_id)
        print(f"Blogger static page {'updated' if page_id else 'published'}: {title}; editor={result.get('editor_url','')}")
        time.sleep(1.0)

    verified: dict[str, dict[str, str]] = {}
    missing: list[str] = []
    # Blogger's public Pages feed is eventually consistent after UI publication.
    # Retry before declaring a newly published page missing; this also prevents
    # duplicate page creation on the next workflow run.
    for attempt in range(1, 9):
        try:
            verified = {item["title"].casefold(): item for item in _public_pages()}
            missing = [page["title"] for page in PAGES if page["title"].casefold() not in verified]
        except Exception as exc:
            missing = [page["title"] for page in PAGES]
            print(f"Blogger public Pages feed verification attempt {attempt}/8 failed: {exc}")
        if not missing:
            break
        print(f"Blogger public Pages feed is still catching up (attempt {attempt}/8); missing={missing}")
        if attempt < 8:
            time.sleep(3)
    if missing:
        raise RuntimeError("Static-page publication verification failed after feed retries; pages not found: " + ", ".join(missing))
    verified_pages = list(verified.values())
    for page in PAGES:
        item = verified[page["title"].casefold()]
        if page["title"] in SERVICE_PAGE_TITLES:
            updated_content = build_service_navigation(
                str(item.get("content", "") or ""), page["title"], verified_pages
            )
            if updated_content != str(item.get("content", "") or ""):
                result = publish_page_ui(
                    title=page["title"], content_html=updated_content,
                    blog_id=blog_id, page_id=item.get("page_id", ""),
                )
                print(f"Blogger service cross-links updated through UI: {page['title']}")
        print(f"Blogger static page verified: {page['title']} -> {item.get('url', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
