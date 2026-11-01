from __future__ import annotations

import base64
import html
import json
import os
import re
import time
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from config import load_blogger_config
from blogger_publisher import blog_id
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row

BLOGGER_EDIT_URL = "https://www.blogger.com/blog/post/edit/{blog_id}/{post_id}?hl=ar"
STORAGE_STATE_FILE = Path(os.getenv("BLOGGER_UI_STORAGE_STATE_FILE", "generated/blogger/browser-state.json"))
META_MAX = 180
RATE_LIMIT_STATUS = "DEFERRED_RATE_LIMIT"
CHALLENGE_MARKERS = (
    "unusual traffic", "automated queries", "verify you are human",
    "verify that you are human", "not a robot", "captcha",
    "traffic from your computer network", "our systems have detected",
    "تحقق من أنك لست روبوت", "حركة مرور غير معتادة",
)


class BloggerRateLimitError(RuntimeError):
    """Raised when Blogger/Google serves a CAPTCHA or rate-limit interstitial."""


def _challenge_reason(page, error: str = "") -> str:
    try:
        current_url = str(getattr(page, "url", "") or "").casefold()
    except Exception:
        current_url = ""
    try:
        body = _clean(page.locator("body").inner_text(timeout=2500)).casefold()
    except Exception:
        body = ""
    haystack = f"{current_url} {body} {str(error or '').casefold()}"
    if any(marker in haystack for marker in CHALLENGE_MARKERS):
        return "Blogger/Google CAPTCHA or unusual-traffic challenge detected; automated edits paused."
    if "google.com/sorry" in current_url:
        return "Google unusual-traffic challenge detected; automated edits paused."
    return ""


def _defer_error(reason: str) -> str:
    retry_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    return f"RETRY_AFTER={retry_at} | {reason}"[:1500]


def _retry_is_due(error: str) -> bool:
    match = re.search(r"RETRY_AFTER=([^|]+)", str(error or ""))
    if not match:
        return False
    try:
        retry_at = datetime.fromisoformat(match.group(1).strip().replace("Z", "+00:00"))
        return retry_at <= datetime.now(timezone.utc)
    except ValueError:
        return False


def _mark_deferred(sheet_service, sheet_id: str, sheet_name: str, candidates, reason: str) -> None:
    deferred_error = _defer_error(reason)
    for row_number, _row in candidates:
        update_row(sheet_service, sheet_id, sheet_name, row_number, {
            "Blogger SEO Status": RATE_LIMIT_STATUS,
            "Blogger SEO Error": deferred_error,
        })


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
    # Blogger changes its labels and panel markup between UI experiments/locales.
    # Try accessible names first, then common input attributes and finally
    # visible editable controls inside the post-settings panel.
    patterns = [
        re.compile(r"search\s*description|وصف\s*البحث|وصف.*البحث", re.I),
        re.compile(r"meta.*description|description.*search|وصف.*محركات البحث", re.I),
    ]
    for pattern in patterns:
        for role in ("textbox", "combobox", "input"):
            try:
                locator = page.get_by_role(role, name=pattern)
                if locator.count():
                    for i in range(min(locator.count(), 8)):
                        candidate = locator.nth(i)
                        if candidate.is_visible() and candidate.is_enabled():
                            return candidate
            except Exception:
                continue
    selectors = [
        'textarea[aria-label*="Search description" i]',
        'textarea[aria-label*="وصف البحث"]',
        'input[aria-label*="Search description" i]',
        'input[aria-label*="وصف البحث"]',
        '[contenteditable="true"][aria-label*="Search description" i]',
        '[contenteditable="true"][aria-label*="وصف البحث"]',
        'textarea[placeholder*="Search description" i]',
        'textarea[placeholder*="وصف البحث"]',
        'input[placeholder*="Search description" i]',
        'input[placeholder*="وصف البحث"]',
        'textarea[name*="description" i]',
        'input[name*="description" i]',
        '[contenteditable="true"][data-placeholder*="description" i]',
        '[contenteditable="true"][data-placeholder*="وصف" i]',
    ]
    # Prefer explicit accessible labels, including labels associated through
    # the HTML <label for=...> relationship.
    for pattern in patterns:
        try:
            locator = page.get_by_label(pattern)
            for i in range(min(locator.count(), 8)):
                candidate = locator.nth(i)
                if candidate.is_visible() and candidate.is_enabled():
                    return candidate
        except Exception:
            continue

    for selector in selectors:
        try:
            locator = page.locator(selector)
            for i in range(min(locator.count(), 8)):
                candidate = locator.nth(i)
                if candidate.is_visible() and candidate.is_enabled():
                    return candidate
        except Exception:
            continue

    # Blogger has changed the field from textarea to input in some editor
    # releases and sometimes drops aria-label/placeholder attributes. Inspect
    # visible editable controls and their associated labels as a final fallback.
    try:
        controls = page.locator('textarea, input:not([type="hidden"]), [contenteditable="true"]')
        for i in range(min(controls.count(), 40)):
            candidate = controls.nth(i)
            if not candidate.is_visible() or not candidate.is_enabled():
                continue
            attrs = " ".join(
                str(candidate.get_attribute(name) or "")
                for name in ("aria-label", "placeholder", "name", "title", "data-placeholder", "aria-labelledby")
            )
            if re.search(r"search.?description|description|وصف|البحث", attrs, re.I):
                return candidate
            try:
                element_id = candidate.get_attribute("id") or ""
                if element_id:
                    label = page.locator(f'label[for="{element_id}"]')
                    if label.count() and re.search(r"search.?description|description|وصف|البحث", label.first.inner_text(), re.I):
                        return candidate
            except Exception:
                pass
    except Exception:
        pass
    return None


def _open_post_settings(page):
    description = _find_description(page)
    if description:
        return description

    panel_selectors = [
        "text=Post settings",
        "text=إعدادات المشاركة",
        "text=إعدادات المنشور",
        "text=إعدادات النشر",
        'button:has-text("Post settings")',
        'button:has-text("إعدادات المشاركة")',
        '[aria-label*="Post settings" i]',
        '[aria-label*="إعدادات المشاركة"]',
    ]
    for selector in panel_selectors:
        try:
            locator = page.locator(selector)
            for index in range(min(locator.count(), 5)):
                candidate = locator.nth(index)
                if candidate.is_visible():
                    candidate.click()
                    page.wait_for_timeout(700)
                    description = _find_description(page)
                    if description:
                        return description
        except Exception:
            continue

    for selector in ("text=Search description", "text=وصف البحث"):
        try:
            locator = page.locator(selector)
            if locator.count() and locator.first.is_visible():
                locator.first.click()
                page.wait_for_timeout(500)
                description = _find_description(page)
                if description:
                    return description
        except Exception:
            continue

    for locator in page.locator('button[aria-label], [role="button"][aria-label]').all():
        try:
            aria = _clean(locator.get_attribute("aria-label") or "")
            if re.search(r"settings|إعدادات|المشاركة", aria, re.I):
                locator.click()
                page.wait_for_timeout(700)
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
        page.get_by_role("button", name=re.compile(r"update|تحديث|تعديل|حفظ|save|publish|نشر", re.I)),
        page.get_by_text(re.compile(r"^\s*(update|تحديث|تعديل|حفظ|save|publish|نشر)\s*$", re.I)),
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
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; KhyratLegalSEO/1.0; +https://askmahmoudkhyrat.blogspot.com/)"
    }
    try:
        response = requests.get(url, headers=headers, timeout=18, allow_redirects=True)
        if response.status_code == 429:
            raise BloggerRateLimitError("Public Blogger page returned HTTP 429 during verification; automated edits paused.")
        response.raise_for_status()
        if re.search("|".join(re.escape(x) for x in CHALLENGE_MARKERS), response.text, re.I):
            raise BloggerRateLimitError("Public Blogger page returned a CAPTCHA/unusual-traffic challenge during verification; automated edits paused.")
        for tag in re.findall(r"<meta\b[^>]*>", response.text, flags=re.I):
            if not re.search(r"""\bname\s*=\s*['"]description['"]""", tag, flags=re.I):
                continue
            match = re.search(r"""\bcontent\s*=\s*(['"])(.*?)\1""", tag, flags=re.I | re.S)
            if match:
                return _clean(html.unescape(match.group(2)))
        return ""
    except BloggerRateLimitError:
        raise
    except Exception:
        # Browser fallback handles transient markup, never a known rate limit.
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        challenge = _challenge_reason(page)
        if challenge:
            raise BloggerRateLimitError(challenge)
        page.wait_for_timeout(700)
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
        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(800)

        challenge = _challenge_reason(page)
        if challenge:
            raise BloggerRateLimitError(challenge)
        if "accounts.google.com" in page.url:
            raise RuntimeError("Blogger UI session is not authenticated; storage state has expired or is invalid.")

        _fill_description(page, description)
        _click_update(page)
        page.wait_for_timeout(1000)

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
        return "VERIFIED"
    except (PlaywrightTimeoutError, Exception) as exc:
        error = str(exc)[:1500]
        challenge = _challenge_reason(page, error)
        if isinstance(exc, BloggerRateLimitError) or challenge:
            reason = challenge or error or "Blogger rate limit detected."
            update_row(sheet_service, sheet_id, sheet_name, row_number, {
                "Blogger SEO Status": RATE_LIMIT_STATUS,
                "Blogger SEO Error": _defer_error(reason),
            })
            print(f"Blogger SEO paused by rate limit: row={row_number}, post={post_id}: {reason}")
            return RATE_LIMIT_STATUS
        # Capture safe UI diagnostics (never cookies, tokens, or browser storage)
        # so a Blogger markup change can be fixed from the next Actions log.
        try:
            body_text = _clean(page.locator("body").inner_text(timeout=3000))[:5000]
            print(f"Blogger SEO UI body text (diagnostic): {body_text}")
            controls = page.locator('input, textarea, [contenteditable="true"], [role="textbox"]')
            control_details = []
            for index in range(min(controls.count(), 40)):
                node = controls.nth(index)
                control_details.append({
                    "tag": node.evaluate("(el) => el.tagName"),
                    "type": node.get_attribute("type"),
                    "aria": node.get_attribute("aria-label"),
                    "placeholder": node.get_attribute("placeholder"),
                    "name": node.get_attribute("name"),
                    "title": node.get_attribute("title"),
                    "role": node.get_attribute("role"),
                })
            print(f"Blogger SEO UI controls (diagnostic): {json.dumps(control_details, ensure_ascii=False)}")
            debug_dir = Path("artifacts/blogger-seo-debug")
            debug_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(debug_dir / f"post-{post_id}.png"), full_page=True)
        except Exception as debug_exc:
            print(f"Blogger SEO UI diagnostics unavailable: {debug_exc}")
        update_row(sheet_service, sheet_id, sheet_name, row_number, {
            "Blogger SEO Status": "FAILED",
            "Blogger SEO Error": error,
        })
        print(f"Blogger SEO failed: row={row_number}, post={post_id}: {error}")
        return "FAILED"


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
        if status == RATE_LIMIT_STATUS and not _retry_is_due(row.get("Blogger SEO Error", "")):
            continue
        if status == "FAILED" and os.getenv("BLOGGER_SEO_RETRY_FAILED", "false").strip().lower() not in {"1", "true", "yes"}:
            continue
        if not _clean(row.get("Blogger Post ID", "")):
            continue
        if not _safe_description(row.get("Blogger Meta Description", "")):
            continue
        candidates.append((row_number, row))

    if not candidates:
        print("Blogger SEO worker: no pending posts.")
        return 0
    candidates.sort(
        key=lambda item: (
            0 if "LEGACY SEO BACKFILL" in _clean(item[1].get("ملاحظات", "")).upper() else 1,
            item[0],
        )
    )

    resolved_blog_id = _clean(config.get("blogger_blog_id", "")) or blog_id(service, config["blogger_url"])
    max_posts = max(1, int(os.getenv("BLOGGER_SEO_MAX_POSTS", "5")))
    candidates = candidates[:max_posts]
    success = 0
    failed = 0
    deferred = 0
    pause_seconds = max(2, min(30, int(os.getenv("BLOGGER_SEO_PAUSE_SECONDS", "6"))))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=storage, locale="ar-EG")
        page = context.new_page()
        for index, (row_number, row) in enumerate(candidates):
            outcome = process_row(page, resolved_blog_id, row_number, row, service, config["sheet_id"], sheet_name)
            if outcome == "VERIFIED":
                success += 1
            elif outcome == RATE_LIMIT_STATUS:
                deferred = 1
                reason = "Batch paused after CAPTCHA/rate-limit detection; retry in a later scheduled run."
                _mark_deferred(service, config["sheet_id"], sheet_name, candidates[index + 1:], reason)
                break
            else:
                failed += 1
            if index < len(candidates) - 1:
                time.sleep(pause_seconds)
        browser.close()

    print(json.dumps({
        "verified": success, "failed": failed, "deferred": deferred,
        "attempted": success + failed + deferred,
        "batch_size": len(candidates), "pause_seconds": pause_seconds,
    }, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
