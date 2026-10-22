from __future__ import annotations

import json

from blogger_seo_audit import norm_title, run


class FakeResponse:
    def __init__(self, url: str, status_code: int, text: str):
        self.url = url
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return json.loads(self.text)


def test_norm_title_collapses_arabic_variants():
    assert norm_title("إجراءات تقسيم التركة") == norm_title("اجراءات تقسيم التركة")


def test_run_reports_duplicate_titles_and_does_not_claim_google_crawl(monkeypatch, tmp_path):
    import blogger_seo_audit as audit

    feed = {
        "feed": {
            "entry": [
                {"title": {"$t": "تقسيم التركة"}, "content": {"$t": "<p>" + ("محتوى قانوني " * 80) + "</p>"},
                 "link": [{"rel": "alternate", "href": "https://askmahmoudkhyrat.blogspot.com/2026/10/a.html"}],
                 "published": {"$t": "2026-10-01T10:00:00Z"}, "updated": {"$t": "2026-10-02T10:00:00Z"}},
                {"title": {"$t": "تقسيم التركة"}, "content": {"$t": "<p>" + ("محتوى قانوني " * 80) + "</p>"},
                 "link": [{"rel": "alternate", "href": "https://askmahmoudkhyrat.blogspot.com/2026/10/b.html"}]},
            ]
        }
    }
    sitemap = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://askmahmoudkhyrat.blogspot.com/2026/10/a.html</loc></url></urlset>'

    def fake_get(url, **kwargs):
        if "feeds/posts/default" in url:
            return FakeResponse(url, 200, json.dumps(feed, ensure_ascii=False))
        if "sitemap.xml" in url:
            return FakeResponse(url, 200, sitemap)
        if "robots.txt" in url:
            return FakeResponse(url, 200, "User-agent: *")
        return FakeResponse(url, 200, "<html>ok</html>")

    monkeypatch.setattr(audit.requests, "get", fake_get)
    monkeypatch.setattr(audit.requests, "Session", lambda: type("Session", (), {
        "headers": {},
        "get": staticmethod(fake_get),
    })())
    report = run(str(tmp_path / "audit"))
    assert report["summary"]["posts_in_feed"] == 2
    assert any(x["code"] == "DUPLICATE_TITLE" for x in report["findings"])
    assert "does not measure Googlebot crawl" in report["important_limit"]
    assert (tmp_path / "audit" / "report.md").exists()
