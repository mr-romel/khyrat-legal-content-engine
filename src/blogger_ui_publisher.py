from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse

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

    # Verify the editor accepted the exact title; a silent field mismatch creates
    # "Untitled" drafts that cannot be matched or safely resumed on the next run.
    try:
        actual_title = loc.input_value(timeout=1200) if loc.evaluate("(el) => el.tagName === 'INPUT'") else loc.inner_text(timeout=1200)
    except Exception:
        actual_title = ""
    normalize = lambda value: re.sub(r"\s+", " ", str(value or "")).strip()
    if normalize(actual_title) != normalize(title):
        try:
            loc.click(timeout=1500)
            page.keyboard.press("Control+A")
            page.keyboard.insert_text(title)
            page.wait_for_timeout(300)
            actual_title = loc.input_value(timeout=1200) if loc.evaluate("(el) => el.tagName === 'INPUT'") else loc.inner_text(timeout=1200)
        except Exception as exc:
            raise BloggerUIPublishError(f"Blogger title field did not retain the requested title: {exc}") from exc
    if normalize(actual_title) != normalize(title):
        raise BloggerUIPublishError(
            f"Blogger title mismatch after filling. expected={title[:140]!r}; actual={actual_title[:140]!r}"
        )
    print(f"Blogger title field verified: {actual_title[:140]}")


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
            "body_excerpt": re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=1500))[:500],
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


def _wait_for_editor_save(page) -> None:
    """Give Blogger's asynchronous draft creation/autosave time before publishing."""
    page.wait_for_timeout(1200)
    try:
        page.wait_for_function(
            """() => !/(creating new post|saving( post)?[.…]*|جارٍ الحفظ|جاري الحفظ)/i.test(
                (document.body && document.body.innerText) || ''
            )""",
            timeout=12000,
        )
        print("Blogger draft creation/autosave indicator cleared before Publish.")
    except PlaywrightTimeoutError:
        try:
            excerpt = re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=1500)).strip()[:700]
        except Exception:
            excerpt = ""
        print("Blogger autosave indicator remained after 12s; waiting once more before Publish: " + excerpt)
        page.wait_for_timeout(3000)


def _click_publish(page) -> None:
    publish_selectors = [
        'button:has-text("Publish")',
        '[role="button"]:has-text("Publish")',
        'button:has-text("نشر")',
        '[role="button"]:has-text("نشر")',
    ]
    button = _first_visible(page, publish_selectors)
    if not button:
        raise BloggerUIPublishError("Blogger UI Publish button was not found.")

    _click_robust(button, "Publish")
    page.wait_for_timeout(1200)
    try:
        after_click_body = re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=1800)).strip()
    except Exception:
        after_click_body = ""
    print(
        "Blogger state immediately after first Publish click: "
        + json.dumps({
            "url": page.url,
            "title": page.title()[:160],
            "body_excerpt": after_click_body[:900],
        }, ensure_ascii=False)
    )

    # Blogger sometimes opens a confirmation dialog. Never click a second
    # generic Publish control in the editor/sidebar: that previously produced
    # dashboard-only ?postId= URLs falsely reported as published.
    dialog = _first_visible(page, [
        '[role="dialog"]',
        '[role="alertdialog"]',
        '[aria-modal="true"]',
        '.modal-dialog',
        '[data-dialog]',
    ])
    if dialog:
        try:
            dialog_text = re.sub(r"\s+", " ", dialog.inner_text(timeout=1200)).strip()
        except Exception:
            dialog_text = ""
        # Current Blogger confirmation dialog labels its affirmative action
        # "CONFIRM", not "Publish". Match that explicit action only inside the
        # dialog that says the post is about to be published.
        confirm = _first_visible(dialog, [
            'button:has-text("Confirm")',
            '[role="button"]:has-text("Confirm")',
            'button:has-text("تأكيد")',
            '[role="button"]:has-text("تأكيد")',
            'button:has-text("Publish")',
            '[role="button"]:has-text("Publish")',
            'button:has-text("نشر")',
            '[role="button"]:has-text("نشر")',
        ])
        cancel = _first_visible(dialog, [
            'button:has-text("Cancel")',
            '[role="button"]:has-text("Cancel")',
            'button:has-text("إلغاء")',
            '[role="button"]:has-text("إلغاء")',
        ])
        has_publish_confirmation = bool(
            confirm and cancel and re.search(r"publish|نشر", dialog_text, re.I)
            and len(dialog_text) < 900
        )
        confirm_html = ""
        if confirm:
            try:
                confirm_html = str(confirm.evaluate("(el) => el.outerHTML"))[:700]
            except Exception:
                pass
        print(
            "Blogger publish dialog inspection: "
            + json.dumps({
                "text": dialog_text[:350],
                "confirm_button": bool(confirm),
                "confirm_html": confirm_html,
                "cancel_button": bool(cancel),
                "recognized_confirmation": has_publish_confirmation,
            }, ensure_ascii=False)
        )
        if has_publish_confirmation:
            _click_robust(confirm, "actual Blogger CONFIRM action")
            page.wait_for_timeout(3200)
            still_visible = _first_visible(page, [
                '[role="dialog"]',
                '[role="alertdialog"]',
                '[aria-modal="true"]',
                '.modal-dialog',
                '[data-dialog]',
            ])
            if still_visible:
                try:
                    remaining = re.sub(r"\s+", " ", still_visible.inner_text(timeout=1000)).strip()
                except Exception:
                    remaining = ""
                if re.search(r"publish post\?|this will publish this post|تأكيد النشر", remaining, re.I):
                    retry_confirm = _first_visible(still_visible, [
                        'button:has-text("CONFIRM")',
                        '[role="button"]:has-text("CONFIRM")',
                        'button:has-text("تأكيد")',
                        '[role="button"]:has-text("تأكيد")',
                    ])
                    if retry_confirm:
                        try:
                            retry_confirm.evaluate("(el) => el.click()")
                            page.wait_for_timeout(2500)
                        except Exception as exc:
                            print(f"Blogger DOM-confirm retry failed: {exc}")
            remaining_dialog = _first_visible(page, [
                '[role="dialog"]',
                '[role="alertdialog"]',
                '[aria-modal="true"]',
                '.modal-dialog',
                '[data-dialog]',
            ])
            if remaining_dialog:
                try:
                    remaining_text = re.sub(r"\s+", " ", remaining_dialog.inner_text(timeout=1000)).strip()
                except Exception:
                    remaining_text = ""
                if re.search(r"publish post\?|this will publish this post|تأكيد النشر", remaining_text, re.I):
                    raise BloggerUIPublishError(
                        "Blogger Publish confirmation remained open after CONFIRM click; refusing to report success. "
                        + remaining_text[:250]
                    )
            print("Blogger publish confirmation completed; dialog is no longer visible.")
    else:
        # Some Blogger builds render a confirmation sheet without dialog roles.
        # Click a second Publish button only when the visible copy explicitly asks
        # to confirm publication, never just because a Publish label exists.
        if re.search(r"publish (this|your) post|ready to publish|publish post now|هل تريد نشر|تأكيد النشر", after_click_body, re.I):
            confirm = _first_visible(page, [
                'button:has-text("Publish")',
                '[role="button"]:has-text("Publish")',
                'button:has-text("نشر")',
                '[role="button"]:has-text("نشر")',
            ])
            if confirm:
                _click_robust(confirm, "Publish confirmation prompt")
                page.wait_for_timeout(1500)


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
            parsed = urlparse(href)
            expected_host = urlparse(blog_url).netloc
            if (
                parsed.scheme in {"http", "https"}
                and parsed.netloc == expected_host
                and not parsed.query
                and re.search(r"/\d{4}/\d{2}/", parsed.path)
                and "/p/" not in parsed.path
            ):
                return href
        except Exception:
            pass

    # If Blogger leaves us on the post editor, derive the private post ID.
    current_url = page.url
    post_match = re.search(r"/blog/post/edit/([0-9]+)/([0-9]+)", current_url)
    if post_match:
        return f"{blog_url.rstrip('/')}/?postId={post_match.group(2)}"

    return ""


def _public_post_permalink(blog_url: str, title: str, attempts: int = 3) -> tuple[str, str]:
    """Resolve a real public permalink and post ID from Blogger's public JSON feed."""
    feed_url = blog_url.rstrip("/") + "/feeds/posts/default"
    wanted = re.sub(r"\s+", " ", str(title or "")).strip().casefold()
    for attempt in range(max(1, attempts)):
        try:
            response = requests.get(
                feed_url,
                params={"alt": "json", "max-results": "100"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; AskMahmoudBloggerPublisher/1.0)"},
                timeout=6,
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
    # Some Blogger blogs disable the Atom/JSON feed. In that case, verify the
    # post through public HTML (home page and Blogger search) instead of treating
    # the private dashboard ?postId= URL as a public link.
    class _AnchorParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.anchors = []
            self._href = None
            self._parts = []

        def handle_starttag(self, tag, attrs):
            if tag.lower() == "a":
                self._href = dict(attrs).get("href", "")
                self._parts = []

        def handle_data(self, data):
            if self._href is not None:
                self._parts.append(data)

        def handle_endtag(self, tag):
            if tag.lower() == "a" and self._href is not None:
                self.anchors.append((self._href, " ".join(" ".join(self._parts).split())))
                self._href = None
                self._parts = []

    wanted = re.sub(r"\s+", " ", str(title or "")).strip().casefold()
    parsed_blog = urlparse(blog_url)
    public_pages = [
        blog_url.rstrip("/") + "/",
        blog_url.rstrip("/") + "/search?q=" + quote(title),
    ]
    for page_url in public_pages:
        try:
            response = requests.get(
                page_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AskMahmoudBloggerPublisher/1.0)"},
                timeout=8,
            )
            response.raise_for_status()
            parser = _AnchorParser()
            parser.feed(response.text)
            for href, anchor_text in parser.anchors:
                absolute = urljoin(page_url, href)
                parsed = urlparse(absolute)
                if parsed.netloc != parsed_blog.netloc or parsed.query or "/p/" in parsed.path:
                    continue
                if not re.search(r"/\d{4}/\d{2}/", parsed.path):
                    continue
                normalized_text = re.sub(r"\s+", " ", anchor_text).strip().casefold()
                if normalized_text == wanted:
                    print(f"Blogger public permalink verified from public HTML: {absolute}")
                    return absolute, ""
        except Exception as exc:
            print(f"Blogger public HTML permalink lookup failed for {page_url}: {exc}")
    print("No public permalink verified by Blogger feed or public HTML.")
    return "", ""


def _dashboard_title_rows(page, title: str) -> list[dict[str, Any]]:
    """Return only links from the specific Blogger row that contains this title."""
    result = page.locator("body").evaluate(
        """body => {
          const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLocaleLowerCase();
          const wanted = norm(TITLE);
          const rows = [];
          const seen = new Set();
          const nodes = Array.from(body.querySelectorAll('a, span, td, [role="row"], div'))
            .filter(el => {
              const raw = el.textContent || '';
              const t = norm(raw);
              return t && raw.length <= wanted.length + 24 && t.length <= wanted.length + 12 &&
                (t === wanted || t.endsWith(wanted) || (el.children.length === 0 && t.includes(wanted)));
            });
          for (const el of nodes) {
            let node = el;
            for (let depth = 0; depth < 8 && node; depth++, node = node.parentElement) {
              const rawRowText = node.textContent || '';
              if (rawRowText.length > 1600) continue;
              const text = norm(rawRowText);
              if (!text || text.length > 1200 || !text.includes(wanted)) continue;
              const links = Array.from(node.querySelectorAll('a[href]')).map(a => ({
                href: a.href || a.getAttribute('href') || '',
                text: (a.innerText || a.textContent || a.getAttribute('aria-label') || '').trim(),
                aria: a.getAttribute('aria-label') || '',
                title: a.getAttribute('title') || ''
              }));
              const edit = links.some(x => /\\/blog\\/post\\/edit\\/\\d+\\/\\d+/.test(x.href));
              if (!edit || links.length > 12) continue;
              const key = text + '|' + links.map(x => x.href).join('|');
              if (!seen.has(key)) {
                seen.add(key);
                rows.push({text: text.slice(0, 500), links});
              }
              if (/(draft|published|scheduled|مسودة|منشور|مجدول)/i.test(text)) break;
            }
          }
          return {candidate_rows: rows.slice(0, 12), body_excerpt: (body.innerText || '').replace(/\\s+/g, ' ').slice(0, 700)};
        }""".replace("TITLE", json.dumps(title, ensure_ascii=False))
    )
    return result.get("candidate_rows", []) if isinstance(result, dict) else []


def _public_permalink_in_browser(page, blog_url: str, title: str, blog_id: str = "") -> str:
    """Resolve a public permalink only from the exact matching Published dashboard row."""
    if not blog_id:
        match = re.search(r"/blog/post/edit/([0-9]+)/", page.url)
        blog_id = match.group(1) if match else ""
    if not blog_id:
        return ""
    try:
        page.goto(f"https://www.blogger.com/blog/posts/{blog_id}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1100)
        if "accounts.google.com" in page.url or "signin" in page.url.lower():
            print("Blogger dashboard permalink lookup skipped: authenticated session expired.")
            return ""
        rows = _dashboard_title_rows(page, title)
        print("Blogger exact-title dashboard rows: " + json.dumps(rows, ensure_ascii=False)[:5000])
        if not rows:
            try:
                excerpt = re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=1500)).strip()[:1600]
            except Exception as exc:
                excerpt = f"dashboard body diagnostic failed: {exc}"
            print("Blogger dashboard had no exact title match; visible posts excerpt: " + excerpt)
        expected_host = urlparse(blog_url).netloc
        for row in rows:
            row_text = str(row.get("text", "")).casefold()
            if not re.search(r"\bpublished\b|منشور", row_text):
                continue
            if not re.search(r"\bdraft\b|مسودة|scheduled|مجدول", row_text):
                continue
            for item in row.get("links", []):
                href = str(item.get("href", "")).strip()
                parsed = urlparse(href)
                if parsed.scheme not in {"http", "https"} or parsed.netloc != expected_host:
                    continue
            if parsed.query or "/p/" in parsed.path or not re.search(r"/\d{4}/\d{2}/", parsed.path):
                    continue
                print(f"Blogger public permalink verified from matching Published dashboard row: {href}")
                return href
        print("No public permalink found in the exact matching Published dashboard row.")
    except Exception as exc:
        print(f"Blogger dashboard permalink lookup failed: {exc}")
    return ""


def _existing_draft_editor_url(page, blog_id: str, title: str) -> str:
    """Reuse the matching draft's edit URL instead of creating another duplicate."""
    try:
        page.goto(f"https://www.blogger.com/blog/posts/{blog_id}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(900)
        rows = _dashboard_title_rows(page, title)
        for row in rows:
            row_text = str(row.get("text", "")).casefold()
            if not re.search(r"\bdraft\b|مسودة", row_text):
                continue
            for item in row.get("links", []):
                href = str(item.get("href", "")).strip()
                if re.search(r"/blog/post/edit/\d+/\d+", href):
                    print("Reusing existing Blogger draft: " + json.dumps({"title": title, "edit_url": href}, ensure_ascii=False))
                    return href
        print(f"No exact matching Blogger draft found for title: {title[:160]}")
    except Exception as exc:
        print(f"Blogger existing-draft lookup failed; will use new-post route: {exc}")
    return ""


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
    browser = None
    context = None
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

            existing_draft_url = _existing_draft_editor_url(page, target_blog_id, title)
            if existing_draft_url:
                editor_url = existing_draft_url
                page.goto(editor_url, wait_until="domcontentloaded")
                print("Blogger publisher opened the matching existing draft instead of creating a duplicate.")
            else:
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
            _wait_for_editor_save(page)
            if search_description.strip():
                # Do not open the unstable Blogger settings sidebar before publishing.
                # It can leave hidden controls over the editor and block the Publish action.
                print("Blogger Search Description deferred; publishing the article takes priority.")
            _click_publish(page)

            page.wait_for_timeout(1200)
            editor_url = page.url
            published_url = _published_url(page, title, blog_url)
            post_id = ""
            match = re.search(r"/blog/post/edit/([0-9]+)/([0-9]+)", editor_url)
            if match:
                post_id = match.group(2)
            browser_permalink = _public_permalink_in_browser(page, blog_url, title, target_blog_id)
            if browser_permalink:
                published_url = browser_permalink

            # The authenticated dashboard row is the preferred verifier when it
            # exposes a public View link for this exact title. Only call public
            # feeds/HTML when the dashboard did not produce a canonical permalink.
            parsed_published = urlparse(published_url)
            if (
                published_url
                and "?postId=" not in published_url
                and parsed_published.netloc == urlparse(blog_url).netloc
                and re.search(r"/\d{4}/\d{2}/", parsed_published.path)
                and "/p/" not in parsed_published.path
            ):
                public_permalink, public_post_id = published_url, ""
            else:
                public_permalink, public_post_id = _public_post_permalink(blog_url, title, attempts=2)
            if public_permalink:
                published_url = public_permalink
                post_id = public_post_id or post_id

            # A private ?postId= URL is not a public permalink. Never report it as
            # published when the public feed could not verify the canonical link.
            if published_url and "?postId=" in published_url:
                published_url = ""
            if not post_id or not published_url:
                raise BloggerUIPublishError(
                    f"Blogger UI publish could not verify a public permalink. Current URL: {page.url}; "
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
        # The enclosing sync_playwright() context owns browser shutdown. Closing
        # these objects here runs after Playwright stops and caused noisy
        # "Event loop is closed" cleanup warnings on every failed publish.
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
