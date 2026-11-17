import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apply_blogger_internal_links import add_related_section, has_internal_related_links


def test_existing_related_heading_without_internal_links_gets_internal_links_appended():
    html = """<article><h2>اقرأ أيضًا</h2><ul><li><a href="https://example.com/external">مصدر خارجي</a></li></ul></article>"""
    related = [
        {"title": "محامي قضايا جنائية", "url": "https://askmahmoudkhyrat.blogspot.com/p/criminal.html"},
        {"title": "الخدمات القانونية", "url": "https://askmahmoudkhyrat.blogspot.com/p/services.html"},
    ]
    assert not has_internal_related_links(html, "https://askmahmoudkhyrat.blogspot.com/")
    updated = add_related_section(html, related)
    assert updated.count("اقرأ أيضًا") == 1
    assert "https://askmahmoudkhyrat.blogspot.com/p/criminal.html" in updated
    assert has_internal_related_links(updated, "https://askmahmoudkhyrat.blogspot.com/")


def test_existing_related_section_with_same_blog_link_is_left_as_complete():
    html = """<article><h2>اقرأ أيضًا</h2><ul><li><a href="https://askmahmoudkhyrat.blogspot.com/2026/11/example.html">مقال داخلي</a></li></ul></article>"""
    assert has_internal_related_links(html, "https://askmahmoudkhyrat.blogspot.com/")


def test_add_related_section_creates_new_section_when_missing():
    html = "<article><p>نص المقال</p></article>"
    related = [{"title": "الخدمات القانونية", "url": "https://askmahmoudkhyrat.blogspot.com/p/services.html"}]
    updated = add_related_section(html, related)
    assert '<section class="khyrat-related-articles">' in updated
    assert updated.count("اقرأ أيضًا") == 1
