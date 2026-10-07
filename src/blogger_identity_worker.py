from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

from blogger_publisher import blog_id, service
from config import load_blogger_config

BLOG_URL = "https://askmahmoudkhyrat.blogspot.com/"
DEFAULT_TITLE = "اسأل محمود - مستشار قانوني للشركات"
DEFAULT_DESCRIPTION = "محتوى قانوني عملي للشركات وأصحاب الأعمال والإدارة والموارد البشرية حول العقود والعمل والشركات والمنازعات والإجراءات القانونية في مصر."
STATE_FILE = Path(os.getenv("BLOGGER_UI_STORAGE_STATE_FILE", "generated/blogger/browser-state.json"))


def _storage_state() -> dict:
    raw = os.getenv("BLOGGER_UI_STORAGE_STATE_B64", "").strip()
    if raw:
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    if STATE_FILE.is_file():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    raise RuntimeError("BLOGGER_UI_STORAGE_STATE_B64 is missing.")


def _clean(v: str) -> str:
    return " ".join(str(v or "").split()).strip()


def _find_field(page, labels: tuple[str, ...], selectors: tuple[str, ...]):
    for label in labels:
        loc = page.get_by_label(re.compile(label, re.I))
        if loc.count():
            return loc.first
        loc = page.get_by_role("textbox", name=re.compile(label, re.I))
        if loc.count():
            return loc.first
    for selector in selectors:
        loc = page.locator(selector)
        if loc.count():
            return loc.first
    return None


def _save(page) -> None:
    for pattern in (r"Save", r"حفظ", r"تحديث", r"Save settings"):
        loc = page.get_by_role("button", name=re.compile(pattern, re.I))
        for i in range(min(loc.count(), 8)):
            candidate = loc.nth(i)
            try:
                if candidate.is_visible() and candidate.is_enabled():
                    candidate.click()
                    page.wait_for_timeout(1200)
                    return
            except Exception:
                pass
    raise RuntimeError("Could not find Blogger settings Save button.")


def main() -> int:
    config = load_blogger_config()
    if not config["enabled"]:
        print("Blogger disabled; identity worker skipped.")
        return 0

    title = _clean(os.getenv("BLOGGER_SITE_TITLE", DEFAULT_TITLE))
    description = _clean(os.getenv("BLOGGER_SITE_DESCRIPTION", DEFAULT_DESCRIPTION))[:180]
    svc = service()
    bid = _clean(config.get("blogger_blog_id", "")) or blog_id(svc, config["blogger_url"])

    urls = [
        f"https://www.blogger.com/blog/settings/{bid}/basic?hl=ar",
        f"https://www.blogger.com/blog/settings/{bid}?hl=ar",
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=_storage_state(), locale="ar-EG")
        page = context.new_page()

        last_error = None
        for url in urls:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1500)
                if "accounts.google.com" in page.url:
                    raise RuntimeError("Blogger UI session is not authenticated.")

                title_field = _find_field(
                    page,
                    (r"Blog title", r"عنوان المدونة", r"العنوان"),
                    ('input[aria-label*="title" i]', 'input[aria-label*="عنوان" i]'),
                )
                desc_field = _find_field(
                    page,
                    (r"Blog description", r"وصف المدونة", r"الوصف"),
                    ('textarea[aria-label*="description" i]', 'textarea[aria-label*="وصف" i]', 'input[aria-label*="description" i]'),
                )
                if not title_field or not desc_field:
                    raise RuntimeError("Blogger Basic settings fields were not found.")

                title_field.fill(title)
                desc_field.fill(description)
                _save(page)

                page.goto(config["blogger_url"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1200)
                actual_title = _clean(page.title())
                meta = page.locator('meta[name="description"]')
                actual_description = _clean(meta.first.get_attribute("content") or "") if meta.count() else ""

                if title not in actual_title:
                    raise RuntimeError(f"Homepage title verification failed: {actual_title!r}")
                if actual_description != description:
                    raise RuntimeError(f"Homepage description verification failed: {actual_description!r}")

                print(f"Blogger identity verified: title={actual_title!r}")
                print(f"Blogger description verified: {actual_description!r}")
                browser.close()
                return 0
            except Exception as exc:
                last_error = exc

        browser.close()
        raise RuntimeError(f"Blogger identity setup failed: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
