from marketplace.discovery import (
    _extract_project_content,
    _legal_score,
    merge_discoveries,
    parse_projects,
    validate_live_projects,
)


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


def test_official_skill_listing_accepts_project_without_keyword():
    html = '<a href="/project/789-business">الانشطة التجارية</a>'
    items = parse_projects(html, official=True)
    assert len(items) == 1
    assert items[0]["source_url"].endswith("/project/789-business")
    assert items[0]["discovery_score"] >= 60


def test_merge_deduplicates_by_source_url():
    old = [{"source_url": "https://mostaql.com/project/1", "title": "قديم", "discovery_score": 20}]
    new = [{"source_url": "https://mostaql.com/project/1", "title": "محدث", "discovery_score": 40}]
    merged = merge_discoveries(old, new)
    assert len(merged) == 1
    assert merged[0]["title"] == "محدث"
    assert merged[0]["discovery_score"] == 40


def test_validate_live_projects_keeps_only_open_resolvable(monkeypatch):
    projects = [
        {"source_url": "https://mostaql.com/project/open", "title": "صياغة عقد"},
        {"source_url": "https://mostaql.com/project/closed", "title": "مراجعة عقد"},
    ]

    def fake_open(url, timeout):
        return url.endswith("/open")

    monkeypatch.setattr("marketplace.discovery._project_is_open", fake_open)
    result = validate_live_projects(projects, limit=10)
    assert len(result) == 1
    assert result[0]["source_url"].endswith("/open")
    assert result[0]["live"] is True


def test_extract_project_content_excludes_platform_chrome():
    page = """# مراجعة عقد عمل

تسجيل الدخول

تفاصيل المشروع

أحتاج مراجعة عقد عمل وصياغة التعديلات القانونية المطلوبة.

المهارات المطلوبة

كتابة محتوى

الميزانية

$25 - $50
"""
    title, description = _extract_project_content(page, "fallback")
    assert title == "مراجعة عقد عمل"
    assert "مراجعة عقد" in description
    assert "تسجيل الدخول" not in description
    assert "الميزانية" not in description


def test_legal_score_does_not_match_generic_platform_text():
    assert _legal_score("محاسبة متجر", "تسجيل الدخول مستقل إنشاء حساب الميزانية") == 0
    assert _legal_score("مراجعة عقد شركة", "أحتاج مراجعة عقد وصياغة تعديلات") >= 70
