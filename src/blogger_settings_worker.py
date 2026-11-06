from __future__ import annotations

import json
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


def _visible_controls(page):
    return page.locator("input,textarea,[contenteditable='true']").evaluate_all(
        """els => els.filter(e => e.getClientRects().length).map(e => ({
          tag:e.tagName, type:e.getAttribute('type'), aria:e.getAttribute('aria-label'),
          placeholder:e.getAttribute('placeholder'), name:e.getAttribute('name'),
          role:e.getAttribute('role'), value:e.value || '', text:(e.innerText || '').slice(0,100)
        })).slice(0,60)"""
    )


def _diagnostics(page, label):
    try:
        data = {
            "label": label,
            "url": page.url,
            "title": page.title(),
            "body": re.sub(r"\\s+", " ", page.locator("body").inner_text(timeout=2500))[:1800],
            "controls": _visible_controls(page),
            "links": page.locator("a").evaluate_all(
                "es => es.filter(e => e.getClientRects().length).map(e => ({text:(e.innerText||'').trim(),href:e.href})).slice(0,35)"
            ),
            "buttons": page.locator("button,[role='button']").evaluate_all(
                "es => es.filter(e => e.getClientRects().length).map(e => ({text:(e.innerText||'').trim(),aria:e.getAttribute('aria-label')})).slice(0,35)"
            ),
        }
    except Exception as exc:
        data = {"label": label, "url": page.url, "error": str(exc)[:500]}
    print("BLOGGER_SETTINGS_DIAGNOSTICS=" + json.dumps(data, ensure_ascii=False))


def _find_field(page, patterns):
    candidates = []
    for selector in ("input", "textarea", "[contenteditable='true']"):
        loc = page.locator(selector)
        for i in range(min(loc.count(), 80)):
            el = loc.nth(i)
            try:
                if not el.is_visible(timeout=250):
                    continue
                meta = " ".join([
                    el.get_attribute("aria-label") or "",
                    el.get_attribute("placeholder") or "",
                    el.get_attribute("name") or "",
                    el.get_attribute("data-placeholder") or "",
                    el.get_attribute("id") or "",
                ])
                if any(re.search(pattern, meta, re.I) for pattern in patterns):
                    candidates.append(el)
            except Exception:
                continue
    return candidates[0] if len(candidates) == 1 else None


def main():
    state = _storage_state_path()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(storage_state=state, locale="ar-EG", viewport={"width": 1440, "height": 1000})
                try:
                    page = context.new_page()
                    page.set_default_timeout(15000)
                    page.goto("https://www.blogger.com/", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2500)
                    if "accounts.google.com" in page.url or "signin" in page.url.lower():
                        _diagnostics(page, "authentication")
                        raise BloggerUIPublishError("Blogger authentication expired or storage state is no longer valid.")

                    bid = _blog_id_from_url(page.url)
                    if not bid:
                        hrefs = page.locator('a[href*="/blog/posts/"],a[href*="/blog/pages/"],a[href*="/blog/settings/"]').evaluate_all("es=>es.map(e=>e.href)")
                        for href in hrefs:
                            bid = _blog_id_from_url(href)
                            if bid:
                                break
                    if not bid:
                        _diagnostics(page, "dashboard-blog-id-resolution")
                        raise BloggerUIPublishError("Could not resolve Blogger blog ID from authenticated dashboard.")

                    settings_url = f"https://www.blogger.com/blog/settings/{bid}"
                    page.goto(settings_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(5000)
                    _diagnostics(page, "settings-page-before-edit")

                    title = _find_field(page, [r"blog.?title", r"^title$", r"عنوان المدونة", r"اسم المدونة"])
                    desc = _find_field(page, [r"blog.?description", r"^description$", r"وصف المدونة"])
                    if title is None or desc is None:
                        raise BloggerUIPublishError(
                            "Settings controls were not uniquely identified. No values were changed; inspect BLOGGER_SETTINGS_DIAGNOSTICS."
                        )

                    title.fill(TITLE)
                    desc.fill(DESCRIPTION)
                    save_candidates = page.get_by_role("button", name=re.compile(r"save|حفظ", re.I))
                    if save_candidates.count() != 1 or not save_candidates.is_visible():
                        _diagnostics(page, "save-control-not-unique")
                        raise BloggerUIPublishError("Could not uniquely identify Save button; no changes submitted.")

                    save_candidates.click()
                    page.wait_for_timeout(3000)
                    page.reload(wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                    _diagnostics(page, "settings-page-after-save")
                    title2 = _find_field(page, [r"blog.?title", r"^title$", r"عنوان المدونة", r"اسم المدونة"])
                    desc2 = _find_field(page, [r"blog.?description", r"^description$", r"وصف المدونة"])
                    if not title2 or not desc2 or title2.input_value() != TITLE or desc2.input_value() != DESCRIPTION:
                        raise BloggerUIPublishError("Settings save could not be verified after reload.")
                    print("BLOGGER_TITLE_DESCRIPTION_UPDATED_AND_VERIFIED")
                finally:
                    context.close()
            finally:
                browser.close()
    finally:
        Path(state).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
