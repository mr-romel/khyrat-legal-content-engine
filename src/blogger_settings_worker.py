from __future__ import annotations

import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright
from blogger_ui_publisher import _storage_state_path, BloggerUIPublishError, _blog_id_from_url

TITLE = "اسأل محمود | محمود خيرت رجب - محامٍ ومستشار قانوني في مصر"
DESCRIPTION = (
    "محمود خيرت رجب، محامٍ ومستشار قانوني في مصر. خدمات قانونية للأفراد والشركات تشمل القضايا المدنية "
    "والتعويضات والجنائية والأسرة والأحوال الشخصية والعمل، وتأسيس الشركات وصياغة العقود ومنازعات الشركات والتجارة "
    "والاستشارات القانونية. متابعة القضايا في القاهرة والجيزة، واستشارات أونلاين في جميع محافظات مصر."
)


def _visible_editors(page):
    candidates = []
    for selector in ("input:not([type=hidden])", "textarea", "[contenteditable=true]", "[role=textbox]"):
        loc = page.locator(selector)
        for i in range(min(loc.count(), 40)):
            el = loc.nth(i)
            try:
                if el.is_visible(timeout=250) and el.is_enabled():
                    candidates.append(el)
            except Exception:
                continue
    # Deduplicate elements that match more than one selector.
    unique = []
    keys = set()
    for el in candidates:
        try:
            key = el.evaluate("(e) => e.tagName + '|' + (e.getAttribute('aria-label')||'') + '|' + (e.getAttribute('name')||'') + '|' + (e.getAttribute('type')||'')")
            if key not in keys:
                keys.add(key)
                unique.append(el)
        except Exception:
            continue
    return unique


def _editor_value(el):
    try:
        return el.input_value(timeout=1000)
    except Exception:
        try:
            return el.inner_text(timeout=1000)
        except Exception:
            return el.get_attribute("value") or ""


def _edit_setting(page, label: str, value: str):
    # Blogger Settings renders Basic > Title/Description as clickable setting rows.
    row = page.get_by_text(label, exact=True)
    if row.count() != 1:
        raise BloggerUIPublishError(f"Expected one '{label}' setting row; found {row.count()}.")
    row.click()
    page.wait_for_timeout(500)

    editors = _visible_editors(page)
    if len(editors) != 1:
        # Prefer the editor inside the active dialog when the page exposes other
        # accessible text controls in its navigation or settings surface.
        dialogs = page.get_by_role("dialog")
        if dialogs.count() == 1:
            scoped = []
            for selector in ("input:not([type=hidden])", "textarea", "[contenteditable=true]", "[role=textbox]"):
                loc = dialogs.locator(selector)
                for i in range(min(loc.count(), 20)):
                    el = loc.nth(i)
                    try:
                        if el.is_visible(timeout=250) and el.is_enabled():
                            scoped.append(el)
                    except Exception:
                        continue
            editors = scoped
    if len(editors) != 1:
        raise BloggerUIPublishError(f"'{label}' edit dialog did not expose exactly one editable field (found {len(editors)}).")

    editor = editors[0]
    editor.fill(value)
    if _editor_value(editor) != value:
        raise BloggerUIPublishError(f"'{label}' value did not remain in the editor; refusing to save.")

    dialogs = page.get_by_role("dialog")
    scope = dialogs if dialogs.count() == 1 else page
    save = scope.get_by_role("button", name=re.compile(r"^(save|حفظ)$", re.I))
    if save.count() != 1 or not save.is_visible():
        raise BloggerUIPublishError(f"Could not uniquely identify the Save button for '{label}'.")
    save.click()
    page.wait_for_timeout(1200)


def _verify_setting(page, label: str, expected: str):
    row = page.get_by_text(label, exact=True)
    if row.count() != 1:
        raise BloggerUIPublishError(f"Could not find the '{label}' row during verification.")
    row.click()
    page.wait_for_timeout(400)
    editors = _visible_editors(page)
    if len(editors) != 1:
        dialogs = page.get_by_role("dialog")
        if dialogs.count() == 1:
            editors = []
            for selector in ("input:not([type=hidden])", "textarea", "[contenteditable=true]", "[role=textbox]"):
                loc = dialogs.locator(selector)
                for i in range(min(loc.count(), 20)):
                    el = loc.nth(i)
                    try:
                        if el.is_visible(timeout=250) and el.is_enabled():
                            editors.append(el)
                    except Exception:
                        continue
    if len(editors) != 1 or _editor_value(editors[0]) != expected:
        actual = _editor_value(editors[0])[:180] if len(editors) == 1 else f"{len(editors)} editors"
        raise BloggerUIPublishError(f"'{label}' verification mismatch: {actual!r}")
    # Close the read-only verification dialog without modifying the setting.
    close = page.get_by_role("button", name=re.compile(r"^(cancel|close|إلغاء|إغلاق)$", re.I))
    if close.count() == 1 and close.is_visible():
        close.click()
    else:
        page.keyboard.press("Escape")
    page.wait_for_timeout(300)


def main():
    state = _storage_state_path()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    storage_state=state,
                    locale="en-GB",
                    viewport={"width": 1440, "height": 1000},
                )
                try:
                    page = context.new_page()
                    page.set_default_timeout(12000)
                    page.goto("https://draft.blogger.com/", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1800)
                    if "accounts.google.com" in page.url or "signin" in page.url.lower():
                        raise BloggerUIPublishError("Blogger authentication expired; no settings were changed.")

                    bid = _blog_id_from_url(page.url)
                    if not bid:
                        links = page.locator('a[href*="/blog/settings/"]').evaluate_all("es => es.map(e => e.href)")
                        for href in links:
                            bid = _blog_id_from_url(href)
                            if bid:
                                break
                    if not bid:
                        raise BloggerUIPublishError("Could not resolve the authenticated Blogger blog ID.")

                    page.goto(f"https://draft.blogger.com/blog/settings/{bid}", wait_until="domcontentloaded", timeout=60000)
                    page.get_by_text("Title", exact=True).wait_for(state="visible", timeout=20000)
                    page.get_by_text("Description", exact=True).wait_for(state="visible", timeout=20000)

                    _edit_setting(page, "Title", TITLE)
                    _edit_setting(page, "Description", DESCRIPTION)

                    page.reload(wait_until="domcontentloaded")
                    page.get_by_text("Title", exact=True).wait_for(state="visible", timeout=20000)
                    _verify_setting(page, "Title", TITLE)
                    _verify_setting(page, "Description", DESCRIPTION)

                    print("BLOGGER_TITLE_DESCRIPTION_UPDATED_AND_VERIFIED")
                finally:
                    context.close()
            finally:
                browser.close()
    finally:
        Path(state).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
