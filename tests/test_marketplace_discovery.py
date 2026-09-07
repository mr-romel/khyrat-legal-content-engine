from marketplace.discovery import merge_discoveries, parse_projects


def test_parse_public_mostaql_projects_and_filter_legal():
    html = '''
    <a href="/project/123-test">مراجعة عقد شركة</a>
    <a href="/project/456-other">تصميم شعار مطعم</a>
    <a href="/project/create">إضافة مشروع</a>
    '''
    items = parse_projects(html)
    assert len(items) == 1
    assert items[0]["platform"] == "mostaql"
    assert items[0]["source_url"].endswith("/project/123-test")
    assert "عقد" in items[0]["title"]


def test_merge_deduplicates_by_source_url():
    old = [{"source_url": "https://mostaql.com/project/1", "title": "قديم", "discovery_score": 20}]
    new = [{"source_url": "https://mostaql.com/project/1", "title": "محدث", "discovery_score": 40}]
    merged = merge_discoveries(old, new)
    assert len(merged) == 1
    assert merged[0]["title"] == "محدث"
    assert merged[0]["discovery_score"] == 40
