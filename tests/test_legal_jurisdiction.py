from legal_jurisdiction import choose_related, jurisdiction


def test_jurisdiction_safe_internal_link_selection():
    source = {"id": "1", "title": "تقسيم التركة وإجراءات الورثة في الجزائر", "content": ""}
    posts = [
        {"id": "1", "title": source["title"], "url": "https://example.com/a"},
        {"id": "2", "title": "إجراءات تقسيم التركة بين الورثة في مصر", "url": "https://example.com/b"},
        {"id": "3", "title": "إجراءات تقسيم التركة بين الورثة في الجزائر", "url": "https://example.com/c"},
    ]
    related = choose_related(source, posts)
    assert [item["url"] for item in related] == ["https://example.com/c"]
    assert jurisdiction("التظلم من القرار الإداري في مصر") == "مصر"
    assert jurisdiction("التظلم من القرار الإداري في الجزائر") == "الجزائر"
