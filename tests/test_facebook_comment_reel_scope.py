from datetime import datetime
from zoneinfo import ZoneInfo

import facebook_private_reply_worker as worker


def test_recent_posts_includes_published_reels_and_posts(monkeypatch):
    now = datetime(2026, 10, 16, 12, 0, tzinfo=ZoneInfo("Africa/Cairo"))
    rows = [
        (2, {
            "Facebook Status": "PUBLISHED",
            "Facebook Post ID": "page_post_1",
            "Reel Status": "PUBLISHED",
            "Reel Facebook ID": "reel_video_1",
            "تاريخ النشر": "2026-10-16",
            "ساعة النشر": "10:00",
            "الموضوع": "اختبار",
        }),
        (3, {
            "Facebook Status": "PUBLISHED",
            "Facebook Post ID": "page_post_2",
            "Reel Status": "REVIEW",
            "Reel Facebook ID": "not_published",
            "تاريخ النشر": "2026-10-15",
            "ساعة النشر": "10:00",
            "الموضوع": "اختبار آخر",
        }),
    ]
    monkeypatch.setattr(worker, "now", lambda: now)
    monkeypatch.setattr(worker, "read_content", lambda *_: rows)
    monkeypatch.setattr(worker, "MAX_RECENT_POSTS", 60)

    targets = worker.recent_posts(object(), "sheet", "Content!A:BC")
    ids = {item[2] for item in targets}

    assert ids == {"page_post_1", "reel_video_1", "page_post_2"}
    assert len(targets) == 3


def test_recent_posts_deduplicates_shared_post_and_reel_id(monkeypatch):
    now = datetime(2026, 10, 16, 12, 0, tzinfo=ZoneInfo("Africa/Cairo"))
    rows = [
        (2, {
            "Facebook Status": "PUBLISHED",
            "Facebook Post ID": "same_platform_id",
            "Reel Status": "PUBLISHED",
            "Reel Facebook ID": "same_platform_id",
            "تاريخ النشر": "2026-10-16",
            "ساعة النشر": "10:00",
        }),
    ]
    monkeypatch.setattr(worker, "now", lambda: now)
    monkeypatch.setattr(worker, "read_content", lambda *_: rows)

    targets = worker.recent_posts(object(), "sheet", "Content!A:BC")

    assert len(targets) == 1
