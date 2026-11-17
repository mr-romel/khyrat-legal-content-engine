from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from blogger_site_setup import PAGES, WHATSAPP
from blogger_pages_ui_worker import build_service_navigation, _page_content, SERVICE_HUB_URL


def test_conversion_service_pages_have_distinct_reader_intent_and_contact_route():
    expected = {
        "الخدمات القانونية للأفراد والشركات",
        "محامي قضايا العمل ومستحقات العامل في مصر",
        "مراجعة وصياغة العقود للشركات والأفراد",
        "الخدمات القانونية للشركات وتأسيسها",
        "قضايا التعويض والمسؤولية المدنية",
    }
    by_title = {page["title"]: page["content"] for page in PAGES}
    assert expected.issubset(by_title)
    for title in expected:
        content = by_title[title]
        assert "<h1>" in content
        assert WHATSAPP in content
        assert "واتساب" in content


def test_service_pages_offer_whatsapp_and_phone_with_ga4_click_intent():
    expected = {
        "الخدمات القانونية للأفراد والشركات",
        "محامي قضايا العمل ومستحقات العامل في مصر",
        "مراجعة وصياغة العقود للشركات والأفراد",
        "الخدمات القانونية للشركات وتأسيسها",
        "قضايا التعويض والمسؤولية المدنية",
    }
    by_title = {page["title"]: page["content"] for page in PAGES}
    for title in expected:
        content = by_title[title]
        assert 'data-contact-method="whatsapp"' in content
        assert 'data-contact-method="phone"' in content
        assert 'href="tel:+201022718375"' in content
        assert "contact_click" in content
        assert "service_page:" in content


def test_service_pages_do_not_promise_legal_outcomes():
    pages = [page for page in PAGES if page["title"] in {
        "الخدمات القانونية للأفراد والشركات",
        "محامي قضايا العمل ومستحقات العامل في مصر",
        "مراجعة وصياغة العقود للشركات والأفراد",
        "الخدمات القانونية للشركات وتأسيسها",
        "قضايا التعويض والمسؤولية المدنية",
    }]
    forbidden = ("نضمن كسب", "مضمون 100%", "نضمن الحكم")
    assert all(not any(term in page["content"] for term in forbidden) for page in pages)



def test_service_navigation_uses_verified_urls_and_is_idempotent():
    from blogger_pages_ui_worker import SERVICE_PAGE_TITLES

    hub = "الخدمات القانونية للأفراد والشركات"
    labor = "محامي قضايا العمل ومستحقات العامل في مصر"
    pages = [
        {"title": hub, "url": "https://askmahmoudkhyrat.blogspot.com/p/services.html"},
        {"title": labor, "url": "https://askmahmoudkhyrat.blogspot.com/p/labor.html"},
        {"title": "صفحة غير مدارة", "url": "https://askmahmoudkhyrat.blogspot.com/p/other.html"},
    ]
    content = build_service_navigation("<article>محتوى</article>", hub, pages)
    assert "https://askmahmoudkhyrat.blogspot.com/p/labor.html" in content
    assert "p/other.html" not in content
    assert labor in content
    again = build_service_navigation(content, hub, pages)
    assert again.count('class="khyrat-service-links"') == 1



def test_managed_page_navigation_exposes_service_hub_without_duplicate_links():
    page = {"content": '<nav aria-label="روابط الموقع"><a href="/">الرئيسية</a></nav><p>محتوى</p>'}
    content = _page_content(page)
    assert SERVICE_HUB_URL in content
    assert "الخدمات القانونية" in content
    again = _page_content({"content": content})
    assert again.count(SERVICE_HUB_URL) == 1



def test_contact_page_has_both_channels_and_idempotent_contact_events():
    import blogger_site_setup

    page = next(item for item in PAGES if item["title"] == "تواصل معنا")
    before = page["content"]
    blogger_site_setup._apply_dual_contact_actions()
    after = page["content"]
    assert 'data-contact-method="whatsapp"' in after
    assert 'data-contact-method="phone"' in after
    assert 'href="tel:+201022718375"' in after
    assert after.count('data-contact-method="phone"') == before.count('data-contact-method="phone"')
    assert "contact_click" in after
