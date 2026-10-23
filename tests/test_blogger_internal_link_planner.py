from blogger_internal_link_planner import build_plan


def test_plan_suggests_related_pages_but_never_publishes():
    audit = {"generated_at": "2026-10-23", "blog_url": "https://example.com", "posts": [
        {"title": "تقسيم التركة وإجراءات الورثة", "url": "https://example.com/a", "internal_links_to_known_posts": []},
        {"title": "إجراءات تقسيم التركة بين الورثة", "url": "https://example.com/b", "internal_links_to_known_posts": []},
        {"title": "إجراءات تأسيس شركة", "url": "https://example.com/c", "internal_links_to_known_posts": []},
    ]}
    plan = build_plan(audit)
    assert plan["posts_in_audit"] == 3
    assert plan["automatically_published"] is False
    assert plan["recommendations"] >= 2
    assert all(item["status"] == "REVIEW_REQUIRED" for item in plan["items"])
    assert all(item["source_url"] != item["target_url"] for item in plan["items"])


def test_plan_skips_existing_internal_links():
    audit = {"posts": [
        {"title": "تقسيم التركة وإجراءات الورثة", "url": "https://example.com/a",
         "internal_links_to_known_posts": ["https://example.com/b?ref=1"]},
        {"title": "إجراءات تقسيم التركة بين الورثة", "url": "https://example.com/b"},
    ]}
    plan = build_plan(audit)
    assert not any(item["source_url"].endswith("/a") and item["target_url"].endswith("/b")
                   for item in plan["items"])
