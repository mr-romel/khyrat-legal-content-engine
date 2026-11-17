from __future__ import annotations

import os
import re
from pathlib import Path
from xml.etree import ElementTree

import requests
from playwright.sync_api import sync_playwright

from blogger_ui_publisher import _storage_state_path, BloggerUIPublishError, _blog_id_from_url

BLOG_URL = os.getenv("BLOGGER_URL", "https://askmahmoudkhyrat.blogspot.com/").strip().rstrip("/")
PHONE = "+201022718375"
WHATSAPP = "201022718375"
MARKER = "KHYRAT_LEGAL_THEME_V2"


CSS = r"""
/* KHYRAT_LEGAL_THEME_V2: conversion + readability layer */
:root{--khyrat-ink:#142b3b;--khyrat-teal:#087f8c;--khyrat-teal-dark:#06636d;--khyrat-gold:#c79a43;--khyrat-paper:#ffffff;--khyrat-muted:#5b6872}
body{color:var(--khyrat-ink);line-height:1.85}
a{transition:color .18s ease,background-color .18s ease,border-color .18s ease}
.kh-contact-top{display:flex;justify-content:center;margin:12px auto 0;padding:0 12px}
.kh-cta{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--khyrat-teal);color:#fff!important;border:1px solid var(--khyrat-teal);border-radius:9px;padding:11px 22px;font-weight:800;text-decoration:none!important;line-height:1.5;box-shadow:0 5px 16px rgba(8,127,140,.16)}
.kh-cta:hover,.kh-cta:focus{background:var(--khyrat-teal-dark);border-color:var(--khyrat-teal-dark);color:#fff!important;text-decoration:none}
.kh-cta-secondary{background:#fff;color:var(--khyrat-teal)!important;border-color:rgba(8,127,140,.35);box-shadow:none}
.kh-home-intro{max-width:980px;margin:26px auto 30px;padding:clamp(22px,4vw,38px);background:linear-gradient(135deg,#f2fbfb 0%,#fff 78%);border:1px solid #dceced;border-radius:18px;text-align:center;box-sizing:border-box}
.kh-home-intro h1{font-size:clamp(25px,4vw,38px);line-height:1.35;color:var(--khyrat-ink);margin:0 0 12px;font-weight:900}
.kh-home-intro p{max-width:760px;margin:0 auto 18px;color:#465963;font-size:17px}
.kh-services{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;max-width:850px;margin:20px auto 22px}
.kh-service{padding:12px 10px;background:#fff;border:1px solid #e3eeee;border-radius:10px;color:#203b49;font-weight:700;font-size:14px}
.kh-post-cta{margin:34px 0 18px;padding:24px clamp(16px,3vw,30px);background:#f1f9f9;border:1px solid #d7e9e9;border-right:4px solid var(--khyrat-gold);border-radius:14px;text-align:center;clear:both}
.kh-post-cta h2{font-size:23px;line-height:1.45;margin:0 0 8px;color:var(--khyrat-ink)}
.kh-post-cta p{margin:0 auto 16px;max-width:720px;color:#4e626c}
.kh-cta-actions{display:flex;justify-content:center;flex-wrap:wrap;gap:10px}
.kh-post-trust{font-size:13px!important;color:#64727a!important;margin-top:12px!important;margin-bottom:0!important}
.kh-mobile-contact{display:none}
@media(max-width:700px){
 .kh-services{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
 .kh-home-intro{margin:16px 12px 22px;border-radius:13px}
 .kh-home-intro p{font-size:15px}
 .kh-post-cta{margin:26px 0 14px;padding:20px 14px}
 .kh-post-cta h2{font-size:20px}
 body.item-view{padding-bottom:66px}
 .kh-mobile-contact{display:flex;position:fixed;z-index:999;bottom:0;left:0;right:0;padding:9px 12px calc(9px + env(safe-area-inset-bottom));background:rgba(255,255,255,.97);border-top:1px solid #dce6e8;box-shadow:0 -4px 18px rgba(20,43,59,.10);justify-content:center}
 .kh-mobile-contact .kh-cta{width:100%;max-width:520px}
}
@media(prefers-reduced-motion:reduce){a{transition:none}}
"""

HEADER_CTA = """
                  <div class='kh-contact-top'>
                    <a class='kh-cta kh-cta-secondary' data-cta-type='consultation' href='https://askmahmoudkhyrat.blogspot.com/p/blog-page_07.html' aria-label='تواصل لطلب استشارة قانونية'>اطلب استشارة قانونية</a>
                  </div>"""

HOME_HERO = """
                <b:if cond='data:view.isHomepage'>
                  <section class='kh-home-intro' aria-labelledby='kh-home-title'>
                    <h1 id='kh-home-title'>معلومة قانونية واضحة.. وخطوة صحيحة في الوقت المناسب</h1>
                    <p>محتوى قانوني متخصص في القانون المصري، مع إمكانية التواصل لعرض المشكلة وتحديد المسار القانوني المناسب وفقًا للمستندات والوقائع.</p>
                    <div class='kh-services'>
                      <div class='kh-service'>القضايا المدنية والتعويضات</div>
                      <div class='kh-service'>القضايا الجنائية</div>
                      <div class='kh-service'>قضايا الأسرة والأحوال الشخصية</div>
                      <div class='kh-service'>تأسيس الشركات وصياغة العقود</div>
                      <div class='kh-service'>منازعات الشركات والتجارة</div>
                      <div class='kh-service'>القضايا العمالية والاستشارات</div>
                    </div>
                    <a class='kh-cta' data-cta-type='consultation' href='https://askmahmoudkhyrat.blogspot.com/p/blog-page_07.html'>تواصل لعرض استفسارك القانوني</a>
                  </section>
                </b:if>"""

POST_CTA = """
  <b:if cond='data:view.isSingleItem'>
    <section class='kh-post-cta' aria-label='طلب استشارة قانونية'>
      <h2>هل تواجه موقفًا قانونيًا مشابهًا؟</h2>
      <p>اعرض الوقائع والمستندات ذات الصلة لبحث الخيارات والإجراءات القانونية الممكنة. تختلف النتيجة بحسب تفاصيل كل حالة.</p>
      <div class='kh-cta-actions'>
        <a class='kh-cta' data-cta-type='consultation' href='https://askmahmoudkhyrat.blogspot.com/p/blog-page_07.html'>اطلب استشارة قانونية</a>
        <a class='kh-cta kh-cta-secondary' href='https://askmahmoudkhyrat.blogspot.com/p/blog-page_980.html'>تصفح الموضوعات القانونية</a>
      </div>
      <p class='kh-post-trust'>المحتوى للتوعية العامة ولا يُعد بديلًا عن فحص المستندات أو استشارة قانونية خاصة.</p>
    </section>
  </b:if>"""

TRACKING_SCRIPT = f"""
    <b:if cond='data:view.isSingleItem'>
      <div class='kh-mobile-contact'>
        <a class='kh-cta' data-cta-type='consultation' href='https://askmahmoudkhyrat.blogspot.com/p/blog-page_07.html'>تواصل الآن لطلب استشارة</a>
      </div>
    </b:if>
    <!-- Khyrat Legal: GA4 lead-event tracking + confirmed phone/WhatsApp. -->
    <script type='text/javascript'><![CDATA[
    window.KH_CONTACT_CONFIG = window.KH_CONTACT_CONFIG || {{ phone: '{PHONE}', whatsapp: '{WHATSAPP}' }};
    (function () {{
      'use strict';
      var config = window.KH_CONTACT_CONFIG || {{}};
      function normalizePhone(value) {{ return String(value || '').replace(/[^+0-9]/g, ''); }}
      function addContactButtons(container) {{
        if (!container || container.querySelector('.kh-direct-contact')) return;
        var phone = normalizePhone(config.phone);
        var whatsapp = String(config.whatsapp || '').replace(/[^0-9]/g, '');
        if (!phone && !whatsapp) return;
        var wrap = document.createElement('span');
        wrap.className = 'kh-direct-contact';
        wrap.style.cssText = 'display:inline-flex;flex-wrap:wrap;justify-content:center;gap:9px;margin:8px 0';
        if (phone) {{
          var call = document.createElement('a');
          call.className = 'kh-cta kh-cta-secondary';
          call.href = 'tel:' + phone;
          call.setAttribute('data-contact-method', 'phone');
          call.textContent = 'اتصل بالمكتب';
          wrap.appendChild(call);
        }}
        if (whatsapp) {{
          var wa = document.createElement('a');
          wa.className = 'kh-cta';
          wa.href = 'https://wa.me/' + whatsapp;
          wa.target = '_blank';
          wa.rel = 'noopener noreferrer';
          wa.setAttribute('data-contact-method', 'whatsapp');
          wa.textContent = 'تواصل عبر واتساب';
          wrap.appendChild(wa);
        }}
        container.appendChild(wrap);
      }}
      function track(name, params) {{
        params = params || {{}};
        params.page_location = window.location.href;
        params.link_url = params.link_url || '';
        window.dataLayer = window.dataLayer || [];
        window.gtag = window.gtag || function () {{ window.dataLayer.push(arguments); }};
        window.gtag('event', name, params);
      }}
      function init() {{
        addContactButtons(document.querySelector('.kh-contact-top'));
        addContactButtons(document.querySelector('.kh-post-cta .kh-cta-actions'));
        addContactButtons(document.querySelector('.kh-mobile-contact'));
        document.addEventListener('click', function (event) {{
          var link = event.target && event.target.closest ? event.target.closest('a') : null;
          if (!link) return;
          var href = link.getAttribute('href') || '';
          var method = link.getAttribute('data-contact-method') || '';
          if (!method && /^tel:/i.test(href)) method = 'phone';
          if (!method && /(?:wa\\.me\\/|api\\.whatsapp\\.com\\/)/i.test(href)) method = 'whatsapp';
          var isContactPage = /\\/p\\/blog-page_07\\.html(?:[?#]|$)/i.test(href);
          if (link.getAttribute('data-cta-type') === 'consultation') {{
            track('consultation_click', {{ contact_method: isContactPage ? 'contact_form' : (method || 'website_cta'), link_url: href }});
          }}
          if (method || isContactPage) {{
            track('contact_click', {{ contact_method: method || 'contact_form', link_url: href }});
          }}
        }}, true);
      }}
      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
      else init();
    }})();
    ]]></script>
"""


def apply_theme_patch(original: str) -> str:
    if MARKER in original:
        return original
    if "]]></b:skin>" not in original:
        raise BloggerUIPublishError("Theme CSS anchor not found; no theme changes were applied.")
    updated = original.replace("]]></b:skin>", CSS + "\n]]></b:skin>", 1)
    updated = updated.replace("http://askmahmoudkhyrat.blogspot.com/", "https://askmahmoudkhyrat.blogspot.com/")
    nav_anchor = updated.find("</nav>", updated.find("id='page_list_top'"))
    if nav_anchor < 0:
        raise BloggerUIPublishError("Header page navigation anchor not found.")
    nav_anchor += len("</nav>")
    updated = updated[:nav_anchor] + HEADER_CTA + updated[nav_anchor:]
    main_anchor = updated.find("<b:if cond='data:view.isMultipleItems'>", updated.find("id='main'"))
    if main_anchor < 0:
        raise BloggerUIPublishError("Homepage hero insertion point not found.")
    updated = updated[:main_anchor] + HOME_HERO + "\n                " + updated[main_anchor:]
    body_anchor = "<data:post.body/>"
    if updated.count(body_anchor) != 1:
        raise BloggerUIPublishError(f"Expected one post-body anchor; found {updated.count(body_anchor)}.")
    updated = updated.replace(body_anchor, body_anchor + POST_CTA, 1)
    script_anchor = "<b:template-script async='true' name='indie' version='1.0.0'/>"
    if updated.count(script_anchor) != 1:
        raise BloggerUIPublishError("Template script insertion point is missing or ambiguous.")
    updated = updated.replace(script_anchor, TRACKING_SCRIPT + "\n    " + script_anchor, 1)
    try:
        ElementTree.fromstring(updated.encode("utf-8"))
    except Exception as exc:
        raise BloggerUIPublishError(f"Updated Blogger theme is not valid XML: {exc}") from exc
    for required in (MARKER, PHONE, WHATSAPP, "contact_click", "consultation_click", "wa.target = '_blank'"):
        if required not in updated:
            raise BloggerUIPublishError(f"Theme patch verification failed: missing {required!r}.")
    return updated


def _editor_value(page) -> tuple[str, str]:
    code_mirror = page.locator(".CodeMirror")
    if code_mirror.count():
        value = code_mirror.first.evaluate("(el) => el.CodeMirror ? el.CodeMirror.getValue() : ''")
        if value:
            return "codemirror", value
    monaco = page.locator(".monaco-editor")
    if monaco.count():
        value = page.evaluate("""() => {
          const editors = window.monaco && window.monaco.editor && window.monaco.editor.getModels();
          return editors && editors.length ? editors[0].getValue() : '';
        }""")
        if value:
            return "monaco", value
    textareas = page.locator("textarea")
    for index in range(min(textareas.count(), 10)):
        el = textareas.nth(index)
        try:
            if el.is_visible(timeout=250):
                value = el.input_value(timeout=1000)
                if len(value) > 10000:
                    return f"textarea:{index}", value
        except Exception:
            continue
    raise BloggerUIPublishError("Blogger HTML editor was not detected; no changes were made.")


def _set_editor_value(page, editor_kind: str, value: str):
    if editor_kind == "codemirror":
        page.locator(".CodeMirror").first.evaluate("(el, value) => el.CodeMirror.setValue(value)", value)
    elif editor_kind == "monaco":
        page.evaluate("""(value) => {
          const editors = window.monaco && window.monaco.editor && window.monaco.editor.getModels();
          if (!editors || !editors.length) throw new Error('Monaco model not found');
          editors[0].setValue(value);
        }""", value)
    elif editor_kind.startswith("textarea:"):
        index = int(editor_kind.split(":", 1)[1])
        page.locator("textarea").nth(index).fill(value)
    else:
        raise BloggerUIPublishError(f"Unsupported Blogger editor type: {editor_kind}")


def main():
    state = _storage_state_path()
    artifact_dir = Path("artifacts/blogger-theme")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(storage_state=state, locale="en-GB", viewport={"width": 1440, "height": 1000})
                try:
                    page = context.new_page()
                    page.set_default_timeout(15000)
                    page.goto("https://draft.blogger.com/", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1500)
                    if "accounts.google.com" in page.url or "signin" in page.url.lower():
                        raise BloggerUIPublishError("Blogger authentication expired; no theme changes were made.")
                    bid = _blog_id_from_url(page.url)
                    if not bid:
                        links = page.locator('a[href*="/blog/settings/"]').evaluate_all("es => es.map(e => e.href)")
                        for href in links:
                            bid = _blog_id_from_url(href)
                            if bid:
                                break
                    if not bid:
                        raise BloggerUIPublishError("Could not resolve authenticated Blogger blog ID.")
                    page.goto(f"https://draft.blogger.com/blog/themes/{bid}", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2000)
                    body = page.locator("body").inner_text(timeout=5000)
                    if "unusual traffic" in body.lower() or "not a robot" in body.lower():
                        raise BloggerUIPublishError("Blogger anti-bot challenge is active; no theme changes were made.")
                    edit = page.get_by_text("Edit HTML", exact=True)
                    if edit.count() == 0:
                        buttons = page.get_by_role("button").all_text_contents()
                        print("BLOGGER_THEME_INSPECT_BUTTONS=" + repr(buttons[:60]))
                        links = page.locator("a").all_text_contents()
                        print("BLOGGER_THEME_INSPECT_LINKS=" + repr(links[:60]))
                        raise BloggerUIPublishError("Edit HTML control not found on Blogger Theme page.")
                    if edit.count() != 1:
                        raise BloggerUIPublishError(f"Edit HTML control is ambiguous: {edit.count()} matches.")
                    edit.click()
                    page.wait_for_timeout(1800)
                    kind, current = _editor_value(page)
                    (artifact_dir / "backup-before.xml").write_text(current, encoding="utf-8")
                    if MARKER in current:
                        updated = current
                    else:
                        updated = apply_theme_patch(current)
                    if os.getenv("BLOGGER_THEME_APPLY", "false").strip().lower() not in {"1", "true", "yes", "on"}:
                        print(f"BLOGGER_THEME_DRY_RUN_OK editor={kind} original_chars={len(current)} updated_chars={len(updated)}")
                        return
                    _set_editor_value(page, kind, updated)
                    save = page.get_by_role("button", name=re.compile(r"^(save|حفظ)$", re.I))
                    if save.count() != 1:
                        raise BloggerUIPublishError(f"Could not uniquely identify Blogger theme Save button: {save.count()}.")
                    save.click()
                    page.wait_for_timeout(5000)
                    page.reload(wait_until="domcontentloaded")
                    page.get_by_text("Edit HTML", exact=True).click()
                    page.wait_for_timeout(1800)
                    verify_kind, saved = _editor_value(page)
                    if MARKER not in saved or PHONE not in saved or "contact_click" not in saved or "consultation_click" not in saved:
                        raise BloggerUIPublishError("Saved theme did not pass Blogger editor read-after-write verification.")
                    (artifact_dir / "updated-theme.xml").write_text(saved, encoding="utf-8")
                    public = requests.get(BLOG_URL + "/", headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                    if public.ok and "unusual traffic" not in public.text.lower():
                        required = ("contact_click", "consultation_click", "phone: '+201022718375'", "whatsapp: '201022718375'")
                        missing = [item for item in required if item not in public.text]
                        if missing:
                            raise BloggerUIPublishError("Public homepage verification missing: " + ", ".join(missing))
                        print("BLOGGER_THEME_PUBLISHED_AND_PUBLICLY_VERIFIED")
                    else:
                        raise BloggerUIPublishError(f"Theme saved in Blogger editor, but public verification failed: HTTP {public.status_code}.")
                finally:
                    context.close()
            finally:
                browser.close()
    finally:
        Path(state).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
