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


def test_related_link_selection_uses_article_context_but_not_generic_title_words():
    source = {
        "id": "1",
        "title": "أثر القرارات في مصر",
        "content": "<article><h2>إجراءات الإفراج الجمركي</h2><p>حظر الاستيراد والسلع المستثناة والرسوم الجمركية.</p></article>",
    }
    posts = [
        {"id": "1", "title": source["title"], "url": "https://example.com/source"},
        {"id": "2", "title": "ضوابط استثناء السلع من حظر الاستيراد والإفراج الجمركي", "url": "https://example.com/customs"},
        {"id": "3", "title": "أثر القرارات على العقود في مصر", "url": "https://example.com/generic"},
    ]
    related = choose_related(source, posts)
    assert [item["url"] for item in related] == ["https://example.com/customs"]
    assert {"السلع", "حظر", "الاستيراد", "الجمركي"} & set(related[0]["shared_terms"])


def test_generic_overlap_words_do_not_create_a_related_link():
    source = {"id": "1", "title": "أثر القرارات وضوابط التعامل القانوني في مصر", "content": ""}
    posts = [
        {"id": "1", "title": source["title"], "url": "https://example.com/a"},
        {"id": "2", "title": "أثر التعامل القانوني والضوابط في مصر", "url": "https://example.com/b"},
    ]
    assert choose_related(source, posts) == []
