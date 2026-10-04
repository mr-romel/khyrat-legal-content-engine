import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from search_console_intelligence import build_opportunities, build_refresh_queue
from blogger_intelligence import related_topics, similarity, inject_internal_links

def test_similarity_and_related_topics_require_real_overlap():
    posts=[{"id":"1","title":"حقوق العامل عند الفصل","url":"https://example.com/a"},
           {"id":"2","title":"تأسيس الشركات","url":"https://example.com/b"}]
    related=related_topics("فصل العامل",posts)
    assert related
    assert related[0]["url"]=="https://example.com/a"
    assert similarity("شيك","تأسيس شركة")==0

def test_internal_links_use_existing_urls_only():
    content="<article><p>نص قانوني</p></article>"
    links=[{"title":"مقال موجود","url":"https://example.com/a"}]
    enriched=inject_internal_links(content,links)
    assert "https://example.com/a" in enriched
    assert "khyrat-related-topics" in enriched

def test_position_8_to_20_becomes_refresh_not_new_article():
    rows=[{"query":"هل يجوز فصل العامل؟","page":"https://example.com/a","clicks":5,
           "impressions":100,"ctr":0.05,"position":12,"intent":"QUESTION","opportunity":60}]
    opportunities=build_opportunities(rows)
    refresh=build_refresh_queue(rows)
    assert opportunities[0][3]=="REFRESH_EXISTING"
    assert refresh[0][0]=="https://example.com/a"

def test_high_value_distant_query_can_be_supporting_article():
    rows=[{"query":"حقوق العامل في الاستقالة","page":"https://example.com/a","clicks":2,
           "impressions":1000,"ctr":0.002,"position":35,"intent":"QUESTION","opportunity":80}]
    opportunities=build_opportunities(rows)
    assert opportunities[0][3]=="CREATE_SUPPORTING_ARTICLE"
