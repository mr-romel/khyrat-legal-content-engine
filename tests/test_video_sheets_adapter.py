from src.video_module.sheets_adapter import posts_from_rows


def test_sheet_adapter_is_read_only_and_maps_common_columns() -> None:
    rows = [
        ["Post ID", "Topic", "Content", "Status", "Published At", "Image URL"],
        ["fb-123", "هل إيصال الأمانة يضمن استرداد الفلوس؟", "محتوى قانوني معتمد", "PUBLISHED", "2026-08-28 19:00", "https://example.com/a.jpg"],
    ]
    posts = posts_from_rows(rows)
    assert len(posts) == 1
    assert posts[0].post_id == "fb-123"
    assert posts[0].status == "PUBLISHED"
    assert posts[0].image_url.endswith("a.jpg")
