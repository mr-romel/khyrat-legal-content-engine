from __future__ import annotations

import base64
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


class BloggerUIPublishError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise BloggerUIPublishError(f"{name} is missing.")
    return value


def _storage_state_path() -> str:
    raw = _required("BLOGGER_UI_STORAGE_STATE_B64")
    try:
        decoded = base64.b64decode(raw, validate=True)
        state = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise BloggerUIPublishError("BLOGGER_UI_STORAGE_STATE_B64 is not valid base64-encoded Playwright storage state JSON.") from exc
    if not isinstance(state, dict) or not isinstance(state.get("cookies"), list):
        raise BloggerUIPublishError("Blogger UI storage state is missing a cookies array.")

    fd, path = tempfile.mkstemp(prefix="blogger-storage-", suffix=".json")
    os.close(fd)
    Path(path).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return path


def _blog_id_from_url(url: str) -> str:
    match = re.search(r"/(?:blog/post/edit|blog/posts|blog/pages)/([0-9]+)", url or "")
    return match.group(1) if match else ""


def _first_visible(page, selectors):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=1500):
                return locator
        except Exception:
            continue
    return None


def _fill_title(page, title: str) -> None:
    loc = _first_visible(page, [
        'input[aria-label*="Title" i]',
        'input[placeholder*="Title" i]',
        'input[aria-label*="العنوان"]',
        'input[placeholder*="العنوان"]',
        'input[name="title"]',
    ])
    if not loc:
        # Blogger's editor DOM changes its aria-labels periodically. Fall back
        # to the first large visible text input, excluding search/login fields.
        candidates = page.locator('input[type="text"], input:not([type]), textarea')
        count = candidates.count()
        for index in range(count):
            candidate = candidates.nth(index)
            try:
                if not candidate.is_visible(timeout=500):
                    continue
                kind = (candidate.get_attribute("type") or "").lower()
                name = " ".join([
                    candidate.get_attribute("aria-label") or "",
                    candidate.get_attribute("placeholder") or "",
                    candidate.get_attribute("name") or "",
                ]).lower()
                if kind in {"search", "email", "password"} or any(x in name for x in ("search", "email", "password")):
                    continue
                box = candidate.bounding_box()
                if box and box["width"] >= 300:
                    loc = candidate
                    break
            except Exception:
                continue
    if not loc:
        raise BloggerUIPublishError("Blogger UI title field was not found.")
    loc.fill(title)


def _set_editor_html(page, content: str) -> None:
    # Blogger can remember HTML mode. Prefer a visible code editor if it is already active.
    direct = _first_visible(page, [
        'textarea[aria-label*="HTML" i]',
        'textarea[aria-label*="html" i]',
        '.CodeMirror textarea',
        '.ace_text-input',
        'textarea',
    ])
    if direct:
        try:
            direct.fill(content)
            return
        except Exception:
            pass

    # Otherwise switch the toolbar's view selector to HTML mode.
    toggles = [
        'button[aria-label*="HTML" i]',
        '[role="button"][aria-label*="HTML" i]',
        'button[title*="HTML" i]',
        '[role="button"][title*="HTML" i]',
        'button[aria-label*="Compose" i]',
        '[role="button"][aria-label*="Compose" i]',
        'button[aria-label*="pencil" i]',
    ]
    toggle = _first_visible(page, toggles)
    if toggle:
        try:
            toggle.click()
            page.wait_for_timeout(400)
            html_option = _first_visible(page, [
                '[role="menuitem"]:has-text("HTML")',
                'text=HTML view',
                'text=HTML',
            ])
            if html_option:
                html_option.click()
                page.wait_for_timeout(500)
        except Exception:
            pass

    direct = _first_visible(page, [
        'textarea[aria-label*="HTML" i]',
        '.CodeMirror textarea',
        '.ace_text-input',
        'textarea',
    ])
    if direct:
        direct.fill(content)
        return

    # Last resort: locate a contenteditable editor, including an editor iframe.
    for frame in page.frames:
        try:
            editor = frame.locator('[contenteditable="true"]').first
            if editor.is_visible(timeout=1000):
                editor.evaluate(
                    """(el, value) => {
                        el.innerHTML = value;
                        el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:null}));
                        el.dispatchEvent(new Event('change', {bubbles:true}));
                    }""",
                    content,
                )
                return
        except Exception:
            continue

    editor = _first_visible(page, ['[contenteditable="true"]'])
    if editor:
        editor.evaluate(
            """(el, value) => {
                el.innerHTML = value;
                el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:null}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
            }""",
            content,
        )
        return

    raise BloggerUIPublishError("Blogger UI post editor was not found.")


def _set_labels(page, labels: list[str]) -> None:
    labels_text = ", ".join(dict.fromkeys(x.strip() for x in labels if x.strip()))
    if not labels_text:
        return
    try:
        button = _first_visible(page, [
            'button[aria-label*="Labels" i]',
            '[role="button"][aria-label*="Labels" i]',
            'button[title*="Labels" i]',
            '[role="button"][title*="Labels" i]',
            'text=Labels',
        ])
        if not button:
            return
        button.click()
        page.wait_for_timeout(250)
        field = _first_visible(page, [
            'input[aria-label*="Labels" i]',
            'input[placeholder*="Labels" i]',
            'textarea[aria-label*="Labels" i]',
        ])
        if field:
            field.fill(labels_text)
            page.keyboard.press("Enter")
            page.wait_for_timeout(200)
    except Exception as exc:
        print(f"Blogger UI labels were not applied: {exc}")


def _click_publish(page) -> None:
    button = _first_visible(page, [
        'button:has-text("Publish")',
        '[role="button"]:has-text("Publish")',
        'button:has-text("نشر")',
        '[role="button"]:has-text("نشر")',
    ])
    if not button:
        raise BloggerUIPublishError("Blogger UI Publish button was not found.")
    button.click()
    page.wait_for_timeout(700)

    # Blogger may ask for confirmation after the first click.
    confirm = _first_visible(page, [
        'button:has-text("Publish")',
        '[role="button"]:has-text("Publish")',
        'button:has-text("نشر")',
        '[role="button"]:has-text("نشر")',
    ])
    if confirm:
        try:
            confirm.click()
        except Exception:
            pass


def _published_url(page, title: str, blog_url: str) -> str:
    # A published confirmation may expose a View link.
    link = _first_visible(page, [
        'a:has-text("View")',
        'a:has-text("عرض")',
        'a[aria-label*="View" i]',
        'a[title*="View" i]',
    ])
    if link:
        try:
            href = str(link.get_attribute("href") or "").strip()
            if href.startswith("http"):
                return href
        except Exception:
            pass

    # If Blogger leaves us on the post editor, derive the private post ID.
    current_url = page.url
    post_match = re.search(r"/blog/post/edit/([0-9]+)/([0-9]+)", current_url)
    if post_match:
        return f"{blog_url.rstrip('/')}/?postId={post_match.group(2)}"

    return ""


def publish_article_ui(
    *,
    title: str,
    content_html: str,
    labels: list[str] | None = None,
    blog_id: str = "",
    blog_url: str = "https://askmahmoudkhyrat.blogspot.com/",
) -> dict[str, str]:
    state_path = _storage_state_path()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(storage_state=state_path, viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.set_default_timeout(15000)

            target_blog_id = str(blog_id or "").strip()
            if not target_blog_id:
                page.goto("https://www.blogger.com/", wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
                target_blog_id = _blog_id_from_url(page.url)

            if not target_blog_id:
                raise BloggerUIPublishError("BLOGGER_BLOG_ID is required for the Blogger UI publisher.")

            editor_url = f"https://www.blogger.com/blog/post/edit/{target_blog_id}/new"
            page.goto(editor_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            if "accounts.google.com" in page.url or "signin" in page.url.lower():
                raise BloggerUIPublishError("Blogger UI storage state is not authenticated or has expired.")

            _fill_title(page, title)
            _set_editor_html(page, content_html)
            _set_labels(page, labels or [])
            _click_publish(page)

            page.wait_for_timeout(1200)
            published_url = _published_url(page, title, blog_url)
            post_id = ""
            match = re.search(r"/blog/post/edit/([0-9]+)/([0-9]+)", page.url)
            if match:
                post_id = match.group(2)

            # The browser must leave a verifiable post/editor URL after publication.
            if not post_id and not published_url:
                raise BloggerUIPublishError(
                    f"Blogger UI publish did not expose a post URL after clicking Publish. Current URL: {page.url}"
                )

            context.close()
            browser.close()
            return {
                "post_id": post_id,
                "post_url": published_url,
                "title": title,
                "publisher": "BROWSER_UI",
            }
    except PlaywrightTimeoutError as exc:
        raise BloggerUIPublishError(f"Blogger UI timed out: {exc}") from exc
    except BloggerUIPublishError:
        raise
    except Exception as exc:
        raise BloggerUIPublishError(f"Blogger UI publication failed: {exc}") from exc
    finally:
        try:
            Path(state_path).unlink(missing_ok=True)
        except Exception:
            pass
