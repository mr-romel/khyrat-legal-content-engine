from scripts.run_blogger_growth_loop import build_growth_snapshot


def test_growth_snapshot_uses_observed_page_and_query_data():
    audit = {
        "summary": {"posts_in_feed": 2},
        "posts": [
            {"title": "تقسيم التركة", "url": "https://example.com/a", "internal_links_to_known_posts": []},
            {"title": "إجراءات تقسيم التركة", "url": "https://example.com/b", "internal_links_to_known_posts": ["https://example.com/a"]},
        ],
        "findings": [],
    }
    pages = [
        {"page": "https://example.com/a", "clicks": 0, "impressions": 120, "ctr": 0, "position": 8},
    ]
    queries = [
        {"query": "تقسيم التركة", "page": "https://example.com/a", "clicks": 0, "impressions": 30, "ctr": 0, "position": 9},
    ]
    result = build_growth_snapshot(audit, pages, queries, "2026-10-01", "2026-10-28")
    assert result["measurement"]["pages_with_data"] == 1
    assert result["measurement"]["queries_with_data"] == 1
    assert result["query_opportunities"][0]["reasons"] == ["LOW_CTR", "STRIKING_DISTANCE"]
    assert result["page_priorities"]["priorities"][0]["url"] == "https://example.com/a"


def test_growth_snapshot_does_not_invent_query_opportunities_when_empty():
    result = build_growth_snapshot({"summary": {}, "posts": [], "findings": []}, [], [], "2026-10-01", "2026-10-28")
    assert result["measurement"]["query_opportunities"] == 0
    assert result["query_opportunities"] == []
