from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import requests
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
    """Return the first visible match, not merely the first (possibly hidden) match."""
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = min(locator.count(), 30)
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible(timeout=500):
                        return candidate
                except Exception:
                    continue
        except Exception:
            continue
    return None


def _click_robust(locator, description: str) -> None:
    """Click a grounded Blogger control, falling back only when overlays intercept it."""
    try:
        locator.click(timeout=5000)
        return
    except Exception as first_exc:
        try:
            locator.click(force=True, timeout=3000)
            print(f"Blogger UI used force-click fallback for {description}: {first_exc}")
            return
        except Exception:
            try:
                locator.evaluate("(el) => el.click()")
                print(f"Blogger UI used DOM-click fallback for {description}.")
                return
            except Exception as final_exc:
                raise BloggerUIPublishError(
                    f"Blogger UI could not click {description}: {str(final_exc)[:400]}"
                ) from final_exc


def _fill_title(page, title: str) -> None:
    loc = _first_visible(page, [
        'input[aria-label*="Title" i]',
        'input[placeholder*="Title" i]',
        'input[aria-label*="العنوان"]',
        'input[placeholder*="العنوان"]',
        'input[name="title"]',
    ])
    if not loc:
        # Blogger's editor DOM changes its aria-labels periodically. Prefer a
        # small visible contenteditable textbox (title) over the large article
        # editor, then fall back to a text input.
        editable = page.locator('[contenteditable="true"]')
        for index in range(editable.count()):
            candidate = editable.nth(index)
            try:
                if not candidate.is_visible(timeout=500):
                    continue
                box = candidate.bounding_box()
                role = (candidate.get_attribute("role") or "").lower()
                name = " ".join([
                    candidate.get_attribute("aria-label") or "",
                    candidate.get_attribute("data-placeholder") or "",
                    candidate.get_attribute("class") or "",
                ]).lower()
                if box and box["width"] >= 300 and box["height"] <= 120 and (
                    role in {"textbox", ""} or "title" in name
                ):
                    loc = candidate
                    break
            except Exception:
                continue

    if not loc:
        candidates = page.locator('input[type="text"], input:not([type]), textarea')
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            try:
                if not candidate.is_visible(timeout=500):
                    continue
                kind = (candidate.get_attribute("type") or "").lower()
                name = " ".join([
                    candidate.get_attribute("aria-label") or "",
                    candidate.get_attribute("placeholder") or "",
                    candidate.get_attribute("name") or "",
                    candidate.get_attribute("class") or "",
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
        try:
            diagnostics = {
                "url": page.url,
                "title": page.title()[:160],
                "buttons": page.locator('[role="button"]').evaluate_all(
                    "els => els.filter(e => e.offsetParent !== null).map(e => ({text:(e.innerText||'').trim(), aria:e.getAttribute('aria-label')})).slice(0,25)"
                ),
                "body_excerpt": re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=1500))[:500],
            }
        except Exception as diagnostic_exc:
            diagnostics = {"url": page.url, "diagnostic_error": str(diagnostic_exc)[:200]}
        print("Blogger title DOM diagnostics: " + json.dumps(diagnostics, ensure_ascii=False))
        raise BloggerUIPublishError(
            "Blogger UI title field was not found. DOM diagnostics: "
            + json.dumps(diagnostics, ensure_ascii=False)[:1000]
        )

    try:
        loc.fill(title, timeout=5000)
    except Exception:
        try:
            loc.evaluate(
                """(el, value) => {
                    if (el.isContentEditable) {
                        el.textContent = value;
                    } else {
                        const setter = Object.getOwnPropertyDescriptor(
                            HTMLInputElement.prototype, "value"
                        )?.set;
                        if (setter) setter.call(el, value);
                        else el.value = value;
                    }
                    el.dispatchEvent(new InputEvent("input", {
                        bubbles: true, inputType: "insertText", data: value
                    }));
                    el.dispatchEvent(new Event("change", {bubbles: true}));
                }""",
                title,
            )
        except Exception as exc:
            raise BloggerUIPublishError(f"Blogger UI title field could not be populated: {exc}") from exc


def _set_editor_html(page, content: str) -> None:
    # Blogger can remember HTML mode. Prefer a visible code editor if it is already active.
    direct = _first_visible(page, [
        'textarea[aria-label*="HTML" i]',
        'textarea[aria-label*="html" i]',
        'textarea[aria-label*="Post body" i]',
        'textarea[aria-label*="محتوى المشاركة"]',
        '[contenteditable="true"][aria-label*="Post body" i]',
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
        'textarea[aria-label*="Post body" i]',
        'textarea[aria-label*="محتوى المشاركة"]',
        '[contenteditable="true"][aria-label*="Post body" i]',
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

    # New Blogger editor builds sometimes expose the body as a large ARIA textbox
    # without contenteditable. Avoid the title field by requiring a large canvas.
    textboxes = page.locator('[role="textbox"]')
    for index in range(textboxes.count()):
        candidate = textboxes.nth(index)
        try:
            if not candidate.is_visible(timeout=500):
                continue
            label = " ".join([
                candidate.get_attribute("aria-label") or "",
                candidate.get_attribute("data-placeholder") or "",
                candidate.get_attribute("class") or "",
            ]).casefold()
            if "title" in label or "العنوان" in label:
                continue
            box = candidate.bounding_box()
            if not box or box["width"] < 450 or box["height"] < 180:
                continue
            candidate.click()
            candidate.fill(content, timeout=5000)
            return
        except Exception:
            continue

    try:
        page_title = page.title()
    except Exception:
        page_title = ""
    try:
        editor_diagnostics = {
            "url": page.url,
            "title": page_title[:160],
            "contenteditable": page.locator('[contenteditable="true"]').count(),
            "textboxes": page.locator('[role="textbox"]').count(),
            "textareas": page.locator("textarea").count(),
            "iframes": page.locator("iframe").count(),
            "body_excerpt": re.sub(r"\\s+", " ", page.locator("body").inner_text(timeout=1500))[:500],
        }
    except Exception as diagnostic_exc:
        editor_diagnostics = {"diagnostic_error": str(diagnostic_exc)[:240], "url": page.url}
    print("Blogger editor DOM diagnostics: " + json.dumps(editor_diagnostics, ensure_ascii=False))
    raise BloggerUIPublishError(
        "Blogger UI post editor was not found. DOM diagnostics: "
        + json.dumps(editor_diagnostics, ensure_ascii=False)[:1200]
    )


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
    _click_robust(button, "Publish")
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
            _click_robust(confirm, "Publish confirmation")
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


def _public_post_permalink(blog_url: str, title: str, attempts: int = 5) -> tuple[str, str]:
    """Resolve a real public permalink and post ID from Blogger's public JSON feed."""
    feed_url = blog_url.rstrip("/") + "/feeds/posts/default"
    wanted = re.sub(r"\s+", " ", str(title or "")).strip().casefold()
    for attempt in range(max(1, attempts)):
        try:
            response = requests.get(
                feed_url,
                params={"alt": "json", "max-results": "100"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; AskMahmoudBloggerPublisher/1.0)"},
                timeout=12,
            )
            response.raise_for_status()
            entries = response.json().get("feed", {}).get("entry", []) or []
            for entry in entries:
                entry_title = re.sub(
                    r"\s+", " ", str((entry.get("title") or {}).get("$t", "") or "")
                ).strip().casefold()
                if entry_title != wanted:
                    continue
                links = entry.get("link", []) or []
                permalink = next(
                    (str(link.get("href", "")).strip() for link in links
                     if link.get("rel") == "alternate" and str(link.get("href", "")).startswith("http")),
                    "",
                )
                raw_id = str((entry.get("id") or {}).get("$t", "") or "")
                match = re.search(r"(?:post-|\.post-)(\d+)$", raw_id)
                post_id = match.group(1) if match else ""
                if permalink:
                    print(f"Blogger public permalink verified from feed: {permalink}")
                    return permalink, post_id
            print(f"Blogger public feed has not exposed the new post yet (attempt {attempt + 1}/{attempts}).")
        except Exception as exc:
            print(f"Blogger public permalink lookup attempt {attempt + 1}/{attempts} failed: {exc}")
        if attempt + 1 < attempts:
            time.sleep(2)
    return "", ""


def publish_article_ui(
    *,
    title: str,
    content_html: str,
    labels: list[str] | None = None,
    blog_id: str = "",
    blog_url: str = "https://askmahmoudkhyrat.blogspot.com/",
    search_description: str = "",
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
            page.wait_for_timeout(1400)

            if "accounts.google.com" in page.url or "signin" in page.url.lower():
                raise BloggerUIPublishError("Blogger UI storage state is not authenticated or has expired.")

            # Current Blogger may redirect the legacy /blog/post/edit/.../new route
            # to the posts dashboard. Open the editor through its visible NEW POST action.
            if not _first_visible(page, [
                'input[aria-label*="Title" i]',
                'input[placeholder*="Title" i]',
                'input[aria-label*="العنوان"]',
                '[contenteditable="true"]',
                'textarea[aria-label*="HTML" i]',
                '[role="textbox"]',
            ]):
                new_post = _first_visible(page, [
                    'button:has-text("New post")',
                    '[role="button"]:has-text("New post")',
                    'a:has-text("New post")',
                    'text=NEW POST',
                    '[aria-label*="New post" i]',
                    'button:has-text("مشاركة جديدة")',
                    '[role="button"]:has-text("مشاركة جديدة")',
                ])
                if new_post:
                    _click_robust(new_post, "New post")
                    page.wait_for_timeout(1800)
                else:
                    # Newer Blogger routes expose the creation action under /blog/posts/{id}/new.
                    page.goto(f"https://www.blogger.com/blog/posts/{target_blog_id}/new", wait_until="domcontentloaded")
                    page.wait_for_timeout(1800)

            # Wait for actual editor controls; a generic dashboard iframe is not an editor.
            try:
                page.wait_for_function(
                    """() => Boolean(
                        document.querySelector('input[aria-label*="Title" i]') ||
                        document.querySelector('input[placeholder*="Title" i]') ||
                        document.querySelector('[contenteditable="true"]') ||
                        document.querySelector('textarea[aria-label*="HTML" i]') ||
                        document.querySelector('[role="textbox"]')
                    )""",
                    timeout=10000,
                )
            except PlaywrightTimeoutError:
                print("Blogger editor controls did not appear before timeout; continuing with expanded selectors.")

            _fill_title(page, title)
            _set_editor_html(page, content_html)
            _set_labels(page, labels or [])
            if search_description.strip():
                # SEO metadata is important, but a changed Blogger sidebar must
                # never prevent the article itself from being published.
                try:
                    from blogger_seo_worker import _fill_description
                    _fill_description(page, search_description.strip()[:180])
                except Exception as exc:
                    print(f"Blogger Search Description could not be set before publish (non-blocking): {exc}")
            _click_publish(page)

            page.wait_for_timeout(1200)
            published_url = _published_url(page, title, blog_url)
            post_id = ""
            match = re.search(r"/blog/post/edit/([0-9]+)/([0-9]+)", page.url)
            if match:
                post_id = match.group(2)

            # Prefer a real public permalink from the feed over Blogger's private
            # dashboard/edit URL or the non-canonical ?postId= fallback.
            public_permalink, public_post_id = _public_post_permalink(blog_url, title)
            if public_permalink:
                published_url = public_permalink
                post_id = public_post_id or post_id

            # Do not report a successful publish unless the post identity can be
            # verified. The feed lookup is retried before this gate.
            if not post_id or not published_url:
                raise BloggerUIPublishError(
                    f"Blogger UI publish could not verify the post ID and URL. Current URL: {page.url}; "
                    f"public permalink found={bool(public_permalink)}"
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


def publish_page_ui(
    *,
    title: str,
    content_html: str,
    blog_id: str,
    page_id: str = "",
) -> dict[str, str]:
    """Create or update a Blogger static page using the authenticated Blogger UI."""
    state_path = _storage_state_path()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=state_path,
                viewport={"width": 1440, "height": 1000},
                locale="ar-EG",
            )
            page = context.new_page()
            page.set_default_timeout(15000)
            target_blog_id = str(blog_id or "").strip()
            if not target_blog_id:
                raise BloggerUIPublishError("BLOGGER_BLOG_ID is required for static-page publication.")

            route = str(page_id or "").strip()
            if route:
                editor_url = f"https://www.blogger.com/blog/page/edit/{target_blog_id}/{route}"
                page.goto(editor_url, wait_until="domcontentloaded")
                page.wait_for_timeout(1400)
            else:
                # As with posts, the legacy /new URL can redirect to the dashboard.
                editor_url = f"https://www.blogger.com/blog/pages/{target_blog_id}"
                page.goto(editor_url, wait_until="domcontentloaded")
                page.wait_for_timeout(1000)
                new_page = _first_visible(page, [
                    'button:has-text("New page")',
                    '[role="button"]:has-text("New page")',
                    'a:has-text("New page")',
                    'text=NEW PAGE',
                    '[aria-label*="New page" i]',
                    'button:has-text("صفحة جديدة")',
                    '[role="button"]:has-text("صفحة جديدة")',
                ])
                if new_page:
                    _click_robust(new_page, "New page")
                    page.wait_for_timeout(1400)
                else:
                    page.goto(f"https://www.blogger.com/blog/page/edit/{target_blog_id}/new", wait_until="domcontentloaded")
                    page.wait_for_timeout(1400)

            if "accounts.google.com" in page.url or "signin" in page.url.lower():
                raise BloggerUIPublishError("Blogger UI storage state is not authenticated or has expired.")

            _fill_title(page, title)
            _set_editor_html(page, content_html)
            action_patterns = (
                'button:has-text("Publish")',
                '[role="button"]:has-text("Publish")',
                'button:has-text("Update")',
                '[role="button"]:has-text("Update")',
                'button:has-text("نشر")',
                '[role="button"]:has-text("نشر")',
                'button:has-text("تحديث")',
                '[role="button"]:has-text("تحديث")',
            )
            action = _first_visible(page, action_patterns)
            if not action:
                raise BloggerUIPublishError("Blogger static-page Publish/Update button was not found.")
            _click_robust(action, "static-page Publish/Update")
            page.wait_for_timeout(800)
            confirm = _first_visible(page, action_patterns)
            if confirm:
                try:
                    _click_robust(confirm, "static-page publish confirmation")
                    page.wait_for_timeout(900)
                except Exception:
                    pass
            current_url = page.url
            match = re.search(r"/blog/page/edit/([0-9]+)/([0-9]+)", current_url)
            resolved_page_id = match.group(2) if match else route
            context.close()
            browser.close()
            return {"page_id": resolved_page_id, "editor_url": current_url, "title": title}
    except PlaywrightTimeoutError as exc:
        raise BloggerUIPublishError(f"Blogger static-page editor timed out: {exc}") from exc
    except BloggerUIPublishError:
        raise
    except Exception as exc:
        raise BloggerUIPublishError(f"Blogger static-page UI publication failed: {exc}") from exc
    finally:
        try:
            Path(state_path).unlink(missing_ok=True)
        except Exception:
            pass


def resolve_blog_id_ui() -> str:
    """Resolve the current Blogger blog ID from the authenticated UI without OAuth API tokens."""
    state_path = _storage_state_path()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(storage_state=state_path, locale="ar-EG")
            page = context.new_page()
            page.goto("https://www.blogger.com/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1200)
            if "accounts.google.com" in page.url or "signin" in page.url.lower():
                raise BloggerUIPublishError("Blogger UI storage state is not authenticated or has expired.")
            value = _blog_id_from_url(page.url)
            if not value:
                # Blogger's dashboard may render the selected blog ID only in a link.
                hrefs = page.locator('a[href*="/blog/posts/"], a[href*="/blog/pages/"]').evaluate_all(
                    "els => els.map(e => e.href)"
                )
                for href in hrefs:
                    value = _blog_id_from_url(str(href))
                    if value:
                        break
            context.close()
            browser.close()
            if not value:
                raise BloggerUIPublishError(f"Could not resolve Blogger blog ID from authenticated UI URL: {page.url}")
            return value
    except BloggerUIPublishError:
        raise
    except Exception as exc:
        raise BloggerUIPublishError(f"Could not resolve Blogger blog ID through UI: {exc}") from exc
    finally:
        try:
            Path(state_path).unlink(missing_ok=True)
        except Exception:
            pass
