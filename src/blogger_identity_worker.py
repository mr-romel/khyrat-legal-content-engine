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

PAGE_TITLES = (
    "من نحن",
    "تواصل معنا",
    "إخلاء المسؤولية القانونية",
    "سياسة الخصوصية",
    "فهرس الموضوعات القانونية",
)


def _storage_state() -> dict:
    raw = os.getenv("BLOGGER_UI_STORAGE_STATE_B64", "").strip()
    if raw:
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    if STATE_FILE.is_file():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    raise RuntimeError("BLOGGER_UI_STORAGE_STATE_B64 is missing.")


def _clean(v: str) -> str:
    return " ".join(str(v or "").split()).strip()


def _visible(loc) -> bool:
    try:
        return loc.count() > 0 and loc.first.is_visible()
    except Exception:
        return False


def _click_first(page, patterns: tuple[str, ...], *, role: str | None = None) -> bool:
    for pattern in patterns:
        try:
            loc = (
                page.get_by_role(role, name=re.compile(pattern, re.I))
                if role
                else page.get_by_text(re.compile(pattern, re.I))
            )
            for i in range(min(loc.count(), 12)):
                candidate = loc.nth(i)
                try:
                    if candidate.is_visible() and candidate.is_enabled():
                        candidate.click()
                        page.wait_for_timeout(900)
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def _click_current_setting_value(page, current_value: str) -> bool:
    current_value = _clean(current_value)
    if not current_value:
        return False
    loc = page.get_by_text(re.compile(rf"^{re.escape(current_value)}$", re.I))
    for i in range(min(loc.count(), 10)):
        candidate = loc.nth(i)
        try:
            if candidate.is_visible() and candidate.is_enabled():
                candidate.click()
                page.wait_for_timeout(700)
                return True
        except Exception:
            continue
    return False


def _edit_current_setting(page, section_label: str, next_label: str, value: str) -> bool:
    body = _clean(page.locator("body").inner_text())
    try:
        current = _clean(body.split(section_label, 1)[1].split(next_label, 1)[0])
    except Exception:
        current = ""
    if not current:
        return False
    if not _click_current_setting_value(page, current):
        return False
    page.wait_for_timeout(600)

    controls = page.locator('input:not([type="hidden"]), textarea, [contenteditable="true"]')
    visible = []
    for i in range(min(controls.count(), 30)):
        c = controls.nth(i)
        try:
            if c.is_visible():
                visible.append(c)
        except Exception:
            pass
    if not visible:
        print(f"Blogger setting dialog for {section_label} has no editable controls.")
        return False

    target = visible[0]
    target.fill(value)
    if not _save_settings(page):
        raise RuntimeError(f"Could not save Blogger {section_label} setting.")
    page.wait_for_timeout(1000)
    return True


def _fill_settings_fields(page, title: str, description: str) -> bool:
    # The current Blogger Arabic UI opens an editor dialog after clicking the
    # displayed value. Edit title and description sequentially.
    title_ok = _edit_current_setting(page, "العنوان", "الوصف", title)
    if not title_ok:
        print("Blogger title setting could not be opened from current value.")
        return False

    # Reload because the title dialog closes after Save and the page state can
    # otherwise retain stale DOM nodes.
    page.reload(wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)

    desc_ok = _edit_current_setting(page, "الوصف", "لغة المدونة", description)
    if not desc_ok:
        print("Blogger description setting could not be opened from current value.")
        return False
    return True



def _save_settings(page) -> bool:
    patterns = (r"Save", r"حفظ", r"تحديث", r"Save settings")
    return _click_first(page, patterns, role="button")


def _set_brand_identity(page, bid: str, title: str, description: str) -> None:
    urls = [
        f"https://www.blogger.com/blog/settings/{bid}/basic?hl=ar",
        f"https://www.blogger.com/blog/settings/{bid}?hl=ar",
    ]
    last_error = None
    for url in urls:
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print(f"Blogger settings navigation: url={page.url} title={page.title()!r} status={(response.status if response else None)}")
            page.screenshot(path="generated/blogger-settings.png", full_page=True)
            page.wait_for_timeout(1800)
            if "accounts.google.com" in page.url:
                raise RuntimeError("Blogger UI session is not authenticated.")
            if _fill_settings_fields(page, title, description):
                if not _save_settings(page):
                    raise RuntimeError("Could not find Blogger settings Save button.")
                print(f"Blogger basic settings saved through {page.url}")
                return
            # Some Blogger themes expose the Page Header widget in Layout
            # rather than the Basic settings form. Let the caller use that path.
            last_error = RuntimeError("Blogger Basic settings fields were not found.")
        except Exception as exc:
            last_error = exc
    if last_error:
        print(f"Blogger Basic settings path unavailable: {last_error}")


def _ensure_pages_gadget(page) -> None:
    layout_urls = [
        f"https://www.blogger.com/blog/layout/{page.get_attribute('data-blog-id') or ''}?hl=ar",
    ]
    # The blog id is injected by the caller through a data attribute only when
    # available; the direct URL below is the reliable Blogger route.
    raise RuntimeError("internal")


def _update_page_header_from_layout(page, title: str, description: str) -> bool:
    # Blogger themes expose the Page Header as a Layout gadget. The edit
    # dialog is more stable than the Basic Settings selectors across themes.
    edits = page.get_by_role("button", name=re.compile(r"تعديل|Edit", re.I))
    for i in range(min(edits.count(), 40)):
        candidate = edits.nth(i)
        try:
            if not candidate.is_visible():
                continue
            candidate.click()
            page.wait_for_timeout(700)
        except Exception:
            continue

        dialogs = page.locator('[role="dialog"], .modal-dialog, .dialog')
        for d_i in range(min(dialogs.count(), 8)):
            dialog = dialogs.nth(d_i)
            try:
                if not dialog.is_visible():
                    continue
                text_blob = _clean(dialog.inner_text())
                if not re.search(r"عنوان المدونة|وصف المدونة|Blog title|Blog description|العنوان|الوصف", text_blob, re.I):
                    continue

                inputs = dialog.locator('input:not([type="hidden"])')
                textareas = dialog.locator("textarea, [contenteditable='true']")
                title_field = None
                desc_field = None
                for j in range(min(inputs.count(), 12)):
                    c = inputs.nth(j)
                    if c.is_visible():
                        title_field = c
                        break
                for j in range(min(textareas.count(), 12)):
                    c = textareas.nth(j)
                    if c.is_visible():
                        desc_field = c
                        break
                if title_field and desc_field:
                    title_field.fill(title)
                    desc_field.fill(description)
                    if not _click_first(dialog, (r"حفظ", r"Save"), role="button"):
                        _click_first(dialog, (r"حفظ", r"Save"))
                    page.wait_for_timeout(900)
                    print("Blogger Page Header title/description updated from Layout.")
                    return True
            except Exception:
                continue

        # Close a non-matching dialog before trying the next gadget.
        _click_first(page, (r"إلغاء", r"Cancel", r"إغلاق", r"Close"), role="button")
    return False


def _ensure_pages_gadget_on_layout(page, bid: str) -> None:
    url = f"https://www.blogger.com/blog/layout/{bid}?hl=ar"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2200)
    if "accounts.google.com" in page.url:
        raise RuntimeError("Blogger UI session is not authenticated.")

    body = _clean(page.locator("body").inner_text())
    has_pages_gadget = any(
        marker in body
        for marker in ("قائمة الصفحات", "Pages gadget", "PageList", "الصفحات")
    )

    if not has_pages_gadget:
        added = _click_first(page, (r"إضافة أداة", r"Add a Gadget"), role="button")
        if not added:
            added = _click_first(page, (r"إضافة أداة", r"Add a Gadget"))
        if not added:
            raise RuntimeError("Blogger Layout: Add a Gadget control not found.")

        if not _click_first(page, (r"الصفحات", r"Pages"), role="button"):
            if not _click_first(page, (r"الصفحات", r"Pages")):
                raise RuntimeError("Blogger Layout: Pages gadget was not found in the gadget picker.")

        page.wait_for_timeout(1200)

    # Whether the gadget was new or already existed, configure visible pages.
    # Current Blogger uses checkboxes in the gadget editor.
    for title in PAGE_TITLES:
        try:
            loc = page.get_by_text(re.compile(rf"^{re.escape(title)}$", re.I))
            for i in range(loc.count()):
                item = loc.nth(i)
                if not item.is_visible():
                    continue
                # Click the associated row/label; this works when the checkbox
                # itself is visually hidden.
                try:
                    item.click()
                    page.wait_for_timeout(150)
                except Exception:
                    pass
                break
        except Exception:
            pass

    # Select unchecked page checkboxes only; avoid toggling already-selected ones.
    checks = page.locator('input[type="checkbox"]')
    for i in range(min(checks.count(), 40)):
        c = checks.nth(i)
        try:
            if c.is_visible() and not c.is_checked():
                c.check()
        except Exception:
            pass

    if not _click_first(page, (r"حفظ", r"Save"), role="button"):
        _click_first(page, (r"حفظ", r"Save"))

    page.wait_for_timeout(1200)
    # Layout itself has a separate Save button on the current Blogger UI.
    _click_first(page, (r"حفظ", r"Save"), role="button")
    page.wait_for_timeout(1500)
    print("Blogger Pages navigation configured and layout save attempted.")


def _verify_public(page, expected_title: str, expected_description: str) -> None:
    response = page.goto(BLOG_URL, wait_until="domcontentloaded", timeout=60000)
    print(f"Blogger public navigation: url={page.url} title={page.title()!r} status={(response.status if response else None)}")
    page.screenshot(path="generated/blogger-public.png", full_page=True)
    page.wait_for_timeout(1500)
    actual_title = _clean(page.title())
    meta = page.locator('meta[name="description"]')
    actual_description = _clean(meta.first.get_attribute("content") or "") if meta.count() else ""
    body = _clean(page.locator("body").inner_text())
    print(f"Blogger public title: {actual_title!r}")
    print(f"Blogger public description: {actual_description!r}")
    print(f"Blogger public page navigation visible: {all(t in body for t in PAGE_TITLES[:2])}")
    if expected_title not in actual_title:
        raise RuntimeError(f"Homepage title verification failed: {actual_title!r}")
    if actual_description and actual_description != expected_description:
        raise RuntimeError(f"Homepage description verification failed: {actual_description!r}")


def main() -> int:
    config = load_blogger_config()
    if not config["enabled"]:
        print("Blogger disabled; identity worker skipped.")
        return 0

    title = _clean(os.getenv("BLOGGER_SITE_TITLE", DEFAULT_TITLE))
    description = _clean(os.getenv("BLOGGER_SITE_DESCRIPTION", DEFAULT_DESCRIPTION))[:180]
    svc = service()
    bid = _clean(config.get("blogger_blog_id", "")) or blog_id(svc, config["blogger_url"])

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=_storage_state(), locale="ar-EG")
        page = context.new_page()

        try:
            _set_brand_identity(page, bid, title, description)
            layout_url = f"https://www.blogger.com/blog/layout/{bid}?hl=ar"
            response = page.goto(layout_url, wait_until="domcontentloaded", timeout=60000)
            print(f"Blogger layout navigation: url={page.url} title={page.title()!r} status={(response.status if response else None)}")
            page.screenshot(path="generated/blogger-layout.png", full_page=True)
            page.wait_for_timeout(1800)
            try:
                print("Blogger Layout body preview:", _clean(page.locator("body").inner_text())[:5000])
            except Exception as exc:
                print(f"Blogger Layout body read failed: {exc}")
            if not _update_page_header_from_layout(page, title, description):
                print("Blogger Page Header gadget was not updated; continuing with navigation setup.")
            _ensure_pages_gadget_on_layout(page, bid)
            _verify_public(page, title, description)
        finally:
            browser.close()

    print("Blogger identity/navigation setup complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
