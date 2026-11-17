import blogger_worker


def test_blogger_articles_get_practice_specific_internal_links(monkeypatch):
    pages = [
        {"title": "محامي قضايا جنائية في القاهرة والجيزة", "url": "https://askmahmoudkhyrat.blogspot.com/p/criminal.html"},
        {"title": "الخدمات القانونية للأفراد والشركات", "url": "https://askmahmoudkhyrat.blogspot.com/p/services.html"},
        {"title": "محامي أحوال شخصية وأسرة في القاهرة والجيزة", "url": "https://askmahmoudkhyrat.blogspot.com/p/family.html"},
    ]
    posts = [
        {"title": "الإجراءات القانونية في المحضر الجنائي", "url": "https://askmahmoudkhyrat.blogspot.com/2026/11/criminal-report.html"},
        {"title": "كيفية تقسيم التركة بين الورثة في الجزائر", "url": "https://askmahmoudkhyrat.blogspot.com/2026/10/deleted-algeria.html"},
    ]
    monkeypatch.setattr(blogger_worker, "_blogger_feed_entries", lambda kind: pages if kind == "pages" else posts)
    related = blogger_worker._related_internal_pages("إجراءات المحضر الجنائي")
    urls = [item["url"] for item in related]
    assert "https://askmahmoudkhyrat.blogspot.com/p/criminal.html" in urls
    assert "https://askmahmoudkhyrat.blogspot.com/p/services.html" in urls
    assert "https://askmahmoudkhyrat.blogspot.com/2026/11/criminal-report.html" in urls
    assert all("deleted-algeria" not in url for url in urls)
    assert len(urls) <= 3


def test_blogger_internal_links_fail_closed_when_public_feed_is_unavailable(monkeypatch):
    def unavailable(_kind):
        raise RuntimeError("feed unavailable")

    monkeypatch.setattr(blogger_worker, "_blogger_feed_entries", unavailable)
    assert blogger_worker._related_internal_pages("قضية جنائية") == []
