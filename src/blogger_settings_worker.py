from __future__ import annotations
import os, re
from pathlib import Path
from playwright.sync_api import sync_playwright
from blogger_ui_publisher import _storage_state_path, BloggerUIPublishError, _blog_id_from_url

TITLE = "اسأل محمود | محمود خيرت رجب - محامٍ ومستشار قانوني في مصر"
DESCRIPTION = ("محمود خيرت رجب، محامٍ ومستشار قانوني في مصر. خدمات قانونية للأفراد والشركات تشمل القضايا المدنية "
"والتعويضات والجنائية والأسرة والأحوال الشخصية والعمل، وتأسيس الشركات وصياغة العقود ومنازعات الشركات والتجارة "
"والاستشارات القانونية. متابعة القضايا في القاهرة والجيزة، واستشارات أونلاين في جميع محافظات مصر.")

def visible(locator):
    try: return locator.count() == 1 and locator.is_visible(timeout=500)
    except Exception: return False

def field(page, patterns):
    matches = []
    for selector in ["input","textarea"]:
        loc = page.locator(selector)
        for i in range(min(loc.count(),50)):
            el=loc.nth(i)
            try:
                if not el.is_visible(): continue
                label=" ".join([el.get_attribute("aria-label") or "",el.get_attribute("placeholder") or "",el.get_attribute("name") or ""])
                if any(re.search(p,label,re.I) for p in patterns): matches.append(el)
            except Exception: pass
    return matches[0] if len(matches)==1 else None

def main():
    state=_storage_state_path(); browser=None; context=None
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            context=browser.new_context(storage_state=state,locale="ar-EG")
            page=context.new_page()
            page.goto("https://www.blogger.com/",wait_until="domcontentloaded",timeout=60000); page.wait_for_timeout(1500)
            if "accounts.google.com" in page.url: raise BloggerUIPublishError("Blogger authentication expired.")
            bid=_blog_id_from_url(page.url)
            if not bid:
                for href in page.locator('a[href*="/blog/posts/"],a[href*="/blog/pages/"]').evaluate_all("es=>es.map(e=>e.href)"):
                    bid=_blog_id_from_url(href)
                    if bid: break
            if not bid: raise BloggerUIPublishError("Could not resolve Blogger blog ID.")
            page.goto(f"https://www.blogger.com/blog/settings/{bid}",wait_until="domcontentloaded",timeout=60000)
            page.wait_for_timeout(2500)
            details=page.locator("input,textarea").evaluate_all("es=>es.filter(e=>e.offsetParent!==null).map(e=>({tag:e.tagName,aria:e.getAttribute('aria-label'),placeholder:e.getAttribute('placeholder'),name:e.getAttribute('name'),value:e.value}))")
            print("VISIBLE SETTINGS FIELDS="+str(details[:40]))
            title=field(page,[r"blog.?title",r"title",r"عنوان المدونة",r"اسم المدونة"])
            desc=field(page,[r"blog.?description",r"description",r"وصف المدونة"])
            if title is None or desc is None:
                raise BloggerUIPublishError("Could not uniquely identify title and description fields; no changes submitted.")
            title.fill(TITLE); desc.fill(DESCRIPTION)
            save=page.get_by_role("button",name=re.compile(r"save|حفظ",re.I))
            if save.count()!=1 or not save.is_visible(): raise BloggerUIPublishError("Could not uniquely identify Save; no changes submitted.")
            save.click(); page.wait_for_timeout(2500); page.reload(wait_until="domcontentloaded"); page.wait_for_timeout(1500)
            title2=field(page,[r"blog.?title",r"title",r"عنوان المدونة",r"اسم المدونة"])
            desc2=field(page,[r"blog.?description",r"description",r"وصف المدونة"])
            if not title2 or not desc2 or title2.input_value()!=TITLE or desc2.input_value()!=DESCRIPTION:
                raise BloggerUIPublishError("Settings save could not be verified after reload.")
            print("BLOGGER_TITLE_DESCRIPTION_UPDATED_AND_VERIFIED")
            print("TITLE="+TITLE); print("DESCRIPTION="+DESCRIPTION)
    finally:
        if context: context.close()
        if browser: browser.close()
        Path(state).unlink(missing_ok=True)

if __name__=="__main__": main()
