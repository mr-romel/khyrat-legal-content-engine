from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from config import load_blogger_config
from blogger_publisher import blog_id
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row

BLOGGER_EDIT_URL = "https://www.blogger.com/blog/post/edit/{blog_id}/{post_id}?hl=ar"
STORAGE_STATE_FILE = Path(os.getenv("BLOGGER_UI_STORAGE_STATE_FILE", "generated/blogger/browser-state.json"))
META_MAX = 180


def _storage_state() -> dict:
    raw = os.getenv("BLOGGER_UI_STORAGE_STATE_B64", "").strip()
    if raw:
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    path = STORAGE_STATE_FILE
    if path.is_file() and path.stat().st_size:
        return json.loads(path.read_text(encoding="utf-8"))
    raise RuntimeError(
        "BLOGGER_UI_STORAGE_STATE_B64 is missing. Create a Playwright storage state "
        "while signed in to the Blogger account and store it as a GitHub Actions secret."
    )


def _clean(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_description(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    value = _clean(value)
    return value[:META_MAX].strip()


def _find_description(page):
    patterns = [
        re.compile(r"search description|وصف البحث|وصف.*البحث", re.I),
        re.compile(r"search.*description", re.I),
    ]
    for pattern in patterns:
        for role in ("textbox", "combobox"):
            locator = page.get_by_role(role, name=pattern)
            if locator.count():
                return locator.first
    selectors = [
        'textarea[aria-label*="Search description" i]',
        'textarea[aria-label*="وصف البحث"]',
        'input[aria-label*="Search description" i]',
        'input[aria-label*="وصف البحث"]',
        '[contenteditable="true"][aria-label*="Search description" i]',
        '[contenteditable="true"][aria-label*="وصف البحث"]',
        'textarea[name*="description" i]',
        'input[name*="description" i]',
    ]
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count():
            return locator.first
    return None


def _open_post_settings(page):
    description = _find_description(page)
    if description:
        return description
    buttons = page.get_by_role("button")
    for label in ("Post settings", "إعدادات المشاركة", "إعدادات المشاركة", "إعدادات المنشور", "Post settings"):
        locator = buttons.filter(has_text=label)
        if locator.count():
            locator.first.click()
            page.wait_for_timeout(500)
            description = _find_description(page)
            if description:
                return description
    # Blogger sometimes exposes the settings panel through a button whose
    # aria-label contains the localized settings text.
    for locator in page.locator('button[aria-label], [role="button"][aria-label]').all():
        try:
            aria = _clean(locator.get_attribute("aria-label") or "")
            if re.search(r"settings|إعدادات|المشاركة", aria, re.I):
                locator.click()
                page.wait_for_timeout(500)
                description = _find_description(page)
                if description:
                    return description
        except Exception:
            continue
    return None


def _fill_description(page, description: str) -> None:
    locator = _open_post_settings(page)
    if locator is None:
        raise RuntimeError("Could not locate Blogger Search Description field in the current UI.")
    locator.scroll_into_view_if_needed()
    try:
        locator.fill(description)
    except Exception:
        locator.click()
        page.keyboard.press("Control+A")
        page.keyboard.type(description)


def _click_update(page) -> None:
    candidates = [
        page.get_by_role("button", name=re.compile(r"update|تحديث|حفظ|save", re.I)),
        page.get_by_text(re.compile(r"^\s*(update|تحديث|حفظ|save)\s*$", re.I)),
    ]
    for locator in candidates:
        if locator.count():
            for i in range(min(locator.count(), 5)):
                candidate = locator.nth(i)
                try:
                    if candidate.is_visible() and candidate.is_enabled():
                        candidate.click()
                        return
                except Exception:
                    continue
    raise RuntimeError("Could not locate Blogger Save/Update control.")


def _read_public_meta(page, url: str) -> str:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)
    locator = page.locator('meta[name="description"]')
    if not locator.count():
        return ""
    return _clean(locator.first.get_attribute("content") or "")


def process_row(page, blog_id: str, row_number: int, row: dict[str, str], sheet_service, sheet_id: str, sheet_name: str) -> bool:
    post_id = _clean(row.get("Blogger Post ID", ""))
    public_url = _clean(row.get("Blogger URL", ""))
    description = _safe_description(row.get("Blogger Meta Description", ""))
    if not post_id or not description:
        return False

    update_row(sheet_service, sheet_id, sheet_name, row_number, {
        "Blogger SEO Status": "PROCESSING",
        "Blogger SEO Error": "",
    })

    edit_url = BLOGGER_EDIT_URL.format(blog_id=blog_id, post_id=post_id)
    try:
        page.goto(edit_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        if "accounts.google.com" in page.url:
            raise RuntimeError("Blogger UI session is not authenticated; storage state has expired or is invalid.")

        _fill_description(page, description)
        _click_update(page)
        page.wait_for_timeout(1500)

        if public_url:
            actual = _read_public_meta(page, public_url)
            if actual != description:
                raise RuntimeError(
                    f"SEO verification mismatch: expected={description!r}, actual={actual!r}"
                )

        update_row(sheet_service, sheet_id, sheet_name, row_number, {
            "Blogger SEO Status": "VERIFIED",
            "Blogger SEO Error": "",
            "Blogger SEO Verified At": datetime.now(timezone.utc).isoformat(),
        })
        print(f"Blogger SEO verified: row={row_number}, post={post_id}")
        return True
    except (PlaywrightTimeoutError, Exception) as exc:
        error = str(exc)[:1500]
        update_row(sheet_service, sheet_id, sheet_name, row_number, {
            "Blogger SEO Status": "FAILED",
            "Blogger SEO Error": error,
        })
        print(f"Blogger SEO failed: row={row_number}, post={post_id}: {error}")
        return False


def main() -> int:
    config = load_blogger_config()
    if not config["enabled"]:
        print("Blogger publishing disabled; SEO worker skipped.")
        return 0

    storage = _storage_state()
    service = create_service(config["service_account_info"])
    sheet_name = config["sheet_range"].split("!", 1)[0]
    ensure_headers(service, config["sheet_id"], sheet_name)
    values = get_values(service, config["sheet_id"], config["sheet_range"])
    if not values:
        print("Blogger SEO worker: no sheet rows.")
        return 0

    rows = [row_to_dict(row) for row in values[1:]]
    candidates = []
    for row_number, row in enumerate(rows, start=2):
        if _clean(row.get("Blogger Status", "")).upper() != "PUBLISHED":
            continue
        status = _clean(row.get("Blogger SEO Status", "")).upper()
        if status == "VERIFIED":
            continue
        if not _clean(row.get("Blogger Post ID", "")):
            continue
        if not _safe_description(row.get("Blogger Meta Description", "")):
            continue
        candidates.append((row_number, row))

    if not candidates:
        print("Blogger SEO worker: no pending posts.")
        return 0

    resolved_blog_id = _clean(config.get("blogger_blog_id", "")) or blog_id(service, config["blogger_url"])
    success = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=storage, locale="ar-EG")
        page = context.new_page()
        for row_number, row in candidates:
            if process_row(page, resolved_blog_id, row_number, row, service, config["sheet_id"], sheet_name):
                success += 1
        browser.close()

    print(f"Blogger SEO worker complete: verified={success}, attempted={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
