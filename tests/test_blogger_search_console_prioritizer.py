from blogger_search_console_prioritizer import prioritize, read_search_console_csv


def test_gsc_csv_normalizes_percent_and_url(tmp_path):
    path = tmp_path / "pages.csv"
    path.write_text("Top pages,Clicks,Impressions,CTR,Position\nhttps://example.com/a/?x=1,5,1000,1.2%,8.5\n", encoding="utf-8")
    rows = read_search_console_csv(str(path))
    assert rows[0]["url"] == "https://example.com/a"
    assert rows[0]["clicks"] == 5
    assert rows[0]["ctr"] == 1.2
    assert rows[0]["position"] == 8.5


def test_prioritizes_impressions_ctr_and_internal_links():
    audit = {"posts": [
        {"title": "تقسيم التركة", "url": "https://example.com/a", "internal_links_to_known_posts": []},
        {"title": "إجراءات تقسيم التركة قانونيا", "url": "https://example.com/b", "internal_links_to_known_posts": ["https://example.com/a"]}],
        "findings": [{"code": "THIN_OR_EMPTY_POST", "url": "https://example.com/a"}]}
    performance = [
        {"url": "https://example.com/a", "clicks": 5, "impressions": 1000, "ctr": 1.0, "position": 8},
        {"url": "https://example.com/b", "clicks": 30, "impressions": 200, "ctr": 10.0, "position": 3}]
    result = prioritize(audit, performance)
    assert result["priorities"][0]["url"] == "https://example.com/a"
    assert "HIGH_IMPRESSIONS_LOW_CTR" in result["priorities"][0]["reasons"]
    assert result["priorities"][0]["suggested_internal_links"][0]["url"] == "https://example.com/b"
