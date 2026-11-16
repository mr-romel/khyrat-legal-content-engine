import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from run_blogger_growth_loop import build_growth_snapshot, classify_indexing_action
from search_console_growth_ledger import build_query_ledger_rows


def test_growth_snapshot_uses_observed_page_and_query_data():
    audit = {
        "summary": {"posts_in_feed": 2},
        "posts": [
            {"title": "تقسيم التركة", "url": "https://example.com/a", "internal_links_to_known_posts": []},
            {"title": "إجراءات تقسيم التركة", "url": "https://example.com/b", "internal_links_to_known_posts": ["https://example.com/a"]},
        ],
        "findings": [],
    }
    pages = [
        {"page": "https://example.com/a", "clicks": 0, "impressions": 120, "ctr": 0, "position": 8},
    ]
    queries = [
        {"query": "تقسيم التركة", "page": "https://example.com/a", "clicks": 0, "impressions": 120, "ctr": 0, "position": 9},
    ]
    result = build_growth_snapshot(audit, pages, queries, "2026-10-01", "2026-10-28")
    assert result["measurement"]["pages_with_data"] == 1
    assert result["measurement"]["queries_with_data"] == 1
    assert result["query_opportunities"][0]["reasons"] == ["LOW_CTR", "STRIKING_DISTANCE"]
    assert result["page_priorities"]["priorities"][0]["url"] == "https://example.com/a"


def test_growth_snapshot_does_not_invent_query_opportunities_when_empty():
    result = build_growth_snapshot({"summary": {}, "posts": [], "findings": []}, [], [], "2026-10-01", "2026-10-28")
    assert result["measurement"]["query_opportunities"] == 0
    assert result["query_opportunities"] == []


def test_page_opportunities_require_observed_search_console_signals():
    audit = {
        "summary": {},
        "posts": [
            {"title": "مقال بلا بيانات", "url": "https://example.com/a", "internal_links_to_known_posts": []},
        ],
        "findings": [],
    }
    result = build_growth_snapshot(audit, [], [], "2026-10-01", "2026-10-28")
    assert result["measurement"]["page_opportunities"] == 0
    assert result["measurement"]["pages_in_technical_backlog"] == 1


def test_growth_snapshot_reports_url_inspection_without_assuming_unknown_is_not_indexed():
    result = build_growth_snapshot(
        {"summary": {}, "posts": [], "findings": []},
        [], [], "2026-10-01", "2026-10-28",
        index_rows=[
            {"url": "https://example.com/a", "verdict": "PASS", "indexing_state": "INDEXING_ALLOWED"},
            {"url": "https://example.com/b", "verdict": "FAIL", "indexing_state": "BLOCKED_BY_META_TAG"},
            {"url": "https://example.com/c", "verdict": "UNKNOWN", "error": "API not enabled"},
        ],
    )
    assert result["url_inspection"]["urls_inspected"] == 3
    assert result["url_inspection"]["indexed_pass"] == 1
    assert result["url_inspection"]["not_indexed_or_blocked"] == 1
    assert result["url_inspection"]["unknown_or_api_error"] == 1


def test_growth_snapshot_compares_equal_previous_window():
    current = [{"page": "https://example.com/a", "clicks": 12, "impressions": 300, "ctr": 0.04, "position": 7}]
    previous = [{"page": "https://example.com/a", "clicks": 8, "impressions": 200, "ctr": 0.04, "position": 9}]
    result = build_growth_snapshot(
        {"summary": {}, "posts": [], "findings": []}, current, [], "2026-10-01", "2026-10-28",
        previous_page_rows=previous,
    )
    assert result["comparison"]["clicks_delta"] == 4
    assert result["comparison"]["impressions_delta"] == 100
    assert result["comparison"]["previous_page_rows"] == 1


def test_ledger_records_only_observed_queries_and_uses_previous_period():
    snapshot = {
        "site": "https://example.com/",
        "generated_at": "2026-11-02T10:00:00+02:00",
        "period": {"start": "2026-10-01", "end": "2026-10-28"},
        "query_metrics": [
            {"query": "إجراءات فصل تعسفي", "page": "https://example.com/a", "clicks": 1,
             "impressions": 250, "ctr": 0.004, "position": 8, "query_page_key": "إجراءات فصل تعسفي||https://example.com/a"},
            {"query": "عبارة بلا ظهور", "page": "https://example.com/b", "clicks": 0,
             "impressions": 0, "ctr": 0, "position": 0, "query_page_key": "عبارة بلا ظهور||https://example.com/b"},
        ],
        "previous_query_metrics": [
            {"query": "إجراءات فصل تعسفي", "page": "https://example.com/a", "clicks": 3,
             "impressions": 200, "ctr": 0.015, "position": 10, "query_page_key": "إجراءات فصل تعسفي||https://example.com/a"},
        ],
    }
    rows = build_query_ledger_rows(snapshot)
    assert len(rows) == 1
    assert rows[0][3] == "إجراءات فصل تعسفي"
    assert rows[0][10] == "قانون العمل"
    assert rows[0][13] in {"REFRESH_EXISTING_PAGE", "IMPROVE_TITLE_AND_SNIPPET"}
    assert rows[0][18] == "-2.0"
    assert rows[0][19] == "50.0"



def test_query_csv_schema_accepts_internal_query_page_key(tmp_path):
    import csv

    from run_blogger_growth_loop import _query

    class QueryRequest:
        def execute(self):
            return {"rows": [{"keys": ["فسخ عقد", "https://example.com/a"], "clicks": 2, "impressions": 10, "ctr": 0.2, "position": 4}]}

    class SearchAnalytics:
        def query(self, **kwargs):
            return QueryRequest()

    class Service:
        def searchanalytics(self):
            return SearchAnalytics()

    rows = _query(Service(), "sc-domain:example.com", "2026-11-01", "2026-11-07", ["query", "page"])
    output = tmp_path / "queries.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["query", "page", "query_page_key", "clicks", "impressions", "ctr", "position"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        saved = list(csv.DictReader(handle))
    assert saved[0]["query_page_key"] == "فسخ عقد||https://example.com/a"


def test_daily_inspection_rotation_returns_40_unique_urls_and_changes_by_day():
    from run_blogger_growth_loop import select_daily_inspection_urls
    urls = [f"https://example.com/{index}" for index in range(128)]
    first = select_daily_inspection_urls(urls, 40, 100)
    next_day = select_daily_inspection_urls(urls, 40, 101)
    assert len(first) == 40
    assert len(set(first)) == 40
    assert len(next_day) == 40
    assert set(first).isdisjoint(set(next_day))


def test_daily_inspection_rotation_deduplicates_and_bounds_limit():
    from run_blogger_growth_loop import select_daily_inspection_urls
    urls = ["https://example.com/a", "https://example.com/a", "https://example.com/b"]
    assert select_daily_inspection_urls(urls, 40, 1) == ["https://example.com/a", "https://example.com/b"]
    assert len(select_daily_inspection_urls(urls * 100, 999, 1)) <= 200


def test_url_inspection_separates_neutral_not_indexed_from_api_errors():
    result = build_growth_snapshot(
        {"summary": {}, "posts": [], "findings": []},
        [], [], "2026-10-01", "2026-10-28",
        index_rows=[
            {"url": "https://example.com/a", "verdict": "NEUTRAL", "coverage_state": "Discovered - currently not indexed"},
            {"url": "https://example.com/b", "verdict": "UNKNOWN", "error": "API unavailable"},
            {"url": "https://example.com/c", "verdict": "PASS"},
        ],
    )
    summary = result["url_inspection"]
    assert summary["neutral_not_yet_indexed_or_decided"] == 1
    assert summary["unknown_or_api_error"] == 1
    assert summary["indexed_pass"] == 1


def test_query_opportunity_requires_enough_impressions_before_ctr_or_position_claim():
    result = build_growth_snapshot(
        {"summary": {}, "posts": [], "findings": []},
        [],
        [{"query": "استشارة قانونية", "page": "https://example.com/a",
          "clicks": 0, "impressions": 19, "ctr": 0, "position": 8}],
        "2026-10-01", "2026-10-28",
    )
    assert result["query_opportunities"] == []
    assert result["measurement"]["queries_below_reliable_sample"] == 1


def test_indexing_action_recommendations_distinguish_discovery_from_quality():
    assert classify_indexing_action({
        "verdict": "NEUTRAL", "coverage_state": "Discovered - currently not indexed"
    }) == "IMPROVE_DISCOVERY_AND_CONTEXTUAL_LINKS"
    assert classify_indexing_action({
        "verdict": "NEUTRAL", "coverage_state": "Crawled - currently not indexed"
    }) == "REVIEW_UNIQUENESS_AND_CONTENT_VALUE"
    assert classify_indexing_action({
        "verdict": "NEUTRAL", "coverage_state": "Duplicate, Google chose different canonical than user"
    }) == "REVIEW_CANONICAL_AND_DUPLICATION"
    assert classify_indexing_action({
        "verdict": "UNKNOWN", "error": "API unavailable"
    }) == "RECHECK_INSPECTION_API"
