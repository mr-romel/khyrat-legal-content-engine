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

    try:
        exact_count = page.locator("body").evaluate(
            """(body, value) => Array.from(body.querySelectorAll('*'))
                .filter(e => (e.textContent || '').trim() === value).length""",
            current_value,
        )
        print(f"Blogger current value DOM matches for {current_value!r}: {exact_count}")
        clicked = page.locator("body").evaluate(
            """(body, value) => {
                const els = Array.from(body.querySelectorAll('*'))
                    .filter(e => (e.textContent || '').trim() === value);
                if (!els.length) return false;
                const el = els.sort((a,b) => a.children.length - b.children.length)[0];
                el.click();
                const parent = el.parentElement;
                if (parent) parent.click();
                return true;
            }""",
            current_value,
        )
        if clicked:
            page.wait_for_timeout(700)
            return True
    except Exception as exc:
        print(f"Blogger DOM click failed for {current_value!r}: {exc}")

    loc = page.get_by_text(re.compile(re.escape(current_value), re.I))
    print(f"Blogger fallback text matches for {current_value!r}: {loc.count()}")
    for i in range(min(loc.count(), 10)):
        candidate = loc.nth(i)
        try:
            if candidate.is_visible():
                candidate.click(force=True)
                page.wait_for_timeout(700)
                return True
        except Exception:
            continue
    return False


def _click_layout_edit_fallback(page, kind: str) -> bool:
    x, y = (947, 452) if kind == "header" else (947, 573)
    try:
        page.mouse.click(x, y)
        page.wait_for_timeout(900)
        print(f"Blogger UI coordinate fallback clicked {kind} editor at {x},{y}.")
        return True
    except Exception as exc:
        print(f"Blogger UI coordinate fallback failed for {kind}: {exc}")
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
        try:
            if section_label == "العنوان":
                page.mouse.click(930, 202)
            else:
                page.mouse.click(900, 275)
            page.wait_for_timeout(700)
        except Exception:
            return False
    page.wait_for_timeout(600)

    controls = page.locator('input:not([type="hidden"]), textarea, [contenteditable="true"]')
    if controls.count() == 0:
        try:
            value_loc = page.get_by_text(re.compile(rf"^{re.escape(current)}$", re.I))
            print(f"Blogger current setting {section_label}: matches={value_loc.count()}")
            if value_loc.count():
                html = value_loc.first.evaluate("(e) => e.parentElement ? e.parentElement.outerHTML : e.outerHTML")
                print("Blogger setting DOM:", html[:8000])
                # Some current Blogger rows put the click target one or two
                # levels above the displayed value.
                for selector in ("xpath=..", "xpath=../..", "xpath=../../.."):
                    try:
                        parent = value_loc.first.locator(selector)
                        if parent.is_visible():
                            parent.click()
                            page.wait_for_timeout(600)
                            controls = page.locator('input:not([type="hidden"]), textarea, [contenteditable="true"]')
                            if controls.count():
                                break
                    except Exception:
                        pass
        except Exception as exc:
            print(f"Blogger setting DOM diagnostic failed: {exc}")
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


def _open_gadget_editor_by_text(page, text_pattern: str) -> bool:
    marker = page.get_by_text(re.compile(text_pattern, re.I))
    for i in range(min(marker.count(), 20)):
        item = marker.nth(i)
        try:
            if not item.is_visible():
                continue
            # The gadget card has a dedicated edit icon/button. Walk upward
            # until we reach the smallest ancestor that owns that button.
            for level in range(1, 7):
                container = item.locator("xpath=" + "/.." * level)
                buttons = container.locator("button")
                if buttons.count() == 0:
                    continue
                for j in range(buttons.count() - 1, -1, -1):
                    button = buttons.nth(j)
                    if button.is_visible() and button.is_enabled():
                        label = (button.get_attribute("aria-label") or "") + " " + (button.get_attribute("title") or "")
                        # Prefer the actual edit control when Blogger exposes it.
                        if label and not re.search(r"edit|تعديل|تحرير", label, re.I):
                            continue
                        button.click()
                        page.wait_for_timeout(900)
                        print(f"Blogger gadget editor opened for {text_pattern}")
                        return True
        except Exception:
            continue
    return False


def _configure_pages_gadget(page) -> bool:
    if not _open_gadget_editor_by_text(page, r"Pages gadget|^مقالات$"):
        if not _click_layout_edit_fallback(page, "pages"):
            print("Blogger Pages gadget editor could not be opened.")
            return False

    page.wait_for_timeout(900)
    dialogs = page.locator('[role="dialog"], .modal-dialog, .dialog, [aria-modal="true"]')
    dialog = None
    for i in range(min(dialogs.count(), 12)):
        d = dialogs.nth(i)
        try:
            if d.is_visible():
                dialog = d
                break
        except Exception:
            pass
    root = dialog or page

    try:
        Path("generated").mkdir(parents=True, exist_ok=True)
        page.screenshot(path="generated/blogger-pages-editor.png", full_page=True)
    except Exception:
        pass

    print("Blogger Pages editor preview:", _clean(root.inner_text())[:7000])

    # Blogger's current Page List editor uses hidden/native checkboxes in some
    # themes. Inspect and click the row whose text contains each target title.
    result = root.locator('input[type="checkbox"]').evaluate_all(
        """els => els.map((e,i) => {
            let p=e;
            for(let n=0;n<5 && p;n++,p=p.parentElement) {
                const t=(p.innerText||'').trim().replace(/\\s+/g,' ');
                if(t.length>0 && t.length<500) return {i,text:t,checked:e.checked,html:e.outerHTML};
            }
            return {i,text:'',checked:e.checked,html:e.outerHTML};
        })"""
    )
    print("Blogger Pages checkbox diagnostics:", json.dumps(result[:80], ensure_ascii=False))

    changed = False
    for title in PAGE_TITLES:
        matched = root.locator('input[type="checkbox"]').evaluate(
            """(els, title) => {
                for (const e of els) {
                    let p=e;
                    for(let n=0;n<7 && p;n++,p=p.parentElement) {
                        const t=(p.innerText||'').trim().replace(/\\s+/g,' ');
                        if(t === title || t.includes(title)) {
                            if(!e.checked) e.click();
                            return true;
                        }
                    }
                }
                return false;
            }""",
            title,
        )
        if matched:
            changed = True
            print(f"Blogger Pages selected: {title}")
        else:
            print(f"Blogger Pages target not found: {title}")

    # Some versions render custom rows without native checkbox elements.
    # Click the exact page label as a secondary path, without toggling arbitrary rows.
    for title in PAGE_TITLES:
        try:
            label = root.get_by_text(re.compile(rf"^{re.escape(title)}$", re.I))
            for i in range(label.count()):
                item = label.nth(i)
                try:
                    if item.is_visible():
                        item.click(force=True)
                        changed = True
                        print(f"Blogger Pages label clicked: {title}")
                        break
                except Exception:
                    pass
        except Exception:
            pass

    if not _click_first(root, (r"حفظ", r"Save"), role="button"):
        _click_first(root, (r"حفظ", r"Save"))
    page.wait_for_timeout(1200)
    return changed

def _update_page_header_from_layout(page, title: str, description: str) -> bool:
    if not _open_gadget_editor_by_text(page, r"Page Header gadget|\\(رأس الصفحة\\).*Ask-Mahmoud|Ask-Mahmoud"):
        if not _click_layout_edit_fallback(page, "header"):
            print("Blogger Header gadget editor could not be opened.")
            return False

    page.wait_for_timeout(900)
    dialogs = page.locator('[role="dialog"], .modal-dialog, .dialog, [aria-modal="true"]')
    root = page
    for i in range(min(dialogs.count(), 12)):
        d = dialogs.nth(i)
        try:
            if d.is_visible():
                root = d
                break
        except Exception:
            pass

    try:
        Path("generated").mkdir(parents=True, exist_ok=True)
        page.screenshot(path="generated/blogger-header-editor.png", full_page=True)
    except Exception:
        pass

    controls = root.locator('input:not([type="hidden"]), textarea, [contenteditable="true"]')
    print(f"Blogger Header editor controls total={controls.count()}")
    diagnostics = controls.evaluate_all(
        """els => els.map((e,i)=>({
            i, tag:e.tagName, type:e.getAttribute('type'), value:e.value||e.innerText||'',
            aria:e.getAttribute('aria-label'), name:e.getAttribute('name'),
            visible:!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length)
        }))"""
    )
    print("Blogger Header controls diagnostics:", json.dumps(diagnostics[:30], ensure_ascii=False))

    editable = [controls.nth(i) for i in range(min(controls.count(), 20))]
    if len(editable) < 2:
        print("Blogger Header editor does not expose two editable fields.")
        return False

    try:
        # Force-fill because Blogger's Material UI may report these inputs as
        # non-visible while they are visibly rendered in the dialog.
        editable[0].fill(title, force=True)
        editable[1].fill(description, force=True)
        if not _click_first(root, (r"حفظ", r"Save"), role="button"):
            _click_first(root, (r"حفظ", r"Save"))
        page.wait_for_timeout(1200)
        print("Blogger Header gadget updated.")
        return True
    except Exception as exc:
        print(f"Blogger Header gadget update failed: {exc}")
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

    _configure_pages_gadget(page)
    page.wait_for_timeout(1200)
    # Layout itself has a separate Save button on the current Blogger UI.
    _click_first(page, (r"حفظ", r"Save"), role="button")
    page.wait_for_timeout(1500)
    try:
        Path("generated").mkdir(parents=True, exist_ok=True)
        page.screenshot(path="generated/blogger-layout-after-save.png", full_page=True)
    except Exception as exc:
        print(f"Blogger layout screenshot failed: {exc}")
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
