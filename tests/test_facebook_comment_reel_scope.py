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



def test_sheet_range_is_widened_for_reel_fields():
    assert worker._include_reel_columns("Content!A:AF") == "Content!A:BC"
    assert worker._include_reel_columns("Content!A:BC") == "Content!A:BC"
    assert worker._include_reel_columns("Content!A:BD") == "Content!A:BD"



def test_list_comments_paginates_beyond_first_page(monkeypatch):
    calls = []

    class Response:
        ok = True
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, *, params, timeout):
        calls.append(dict(params))
        if len(calls) == 1:
            return Response({
                "data": [{"id": "comment_1"}],
                "paging": {"next": "https://example.invalid/page", "cursors": {"after": "cursor_2"}},
            })
        return Response({"data": [{"id": "comment_2"}]})

    monkeypatch.setattr(worker.requests, "get", fake_get)
    comments, status, error = worker.list_comments("post_1", "test-token")

    assert [item["id"] for item in comments] == ["comment_1", "comment_2"]
    assert status == 200
    assert error == ""
    assert len(calls) == 2
    assert calls[1]["after"] == "cursor_2"
