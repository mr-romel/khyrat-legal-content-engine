from search_console_intelligence import build_opportunities


def test_opportunity_ids_are_stable_across_processes():
    rows = [{
        "query": "ما شروط عقد العمل؟",
        "page": "https://example.com/work-contract",
        "clicks": 2,
        "impressions": 150,
        "ctr": 0.01,
        "position": 12,
        "intent": "QUESTION",
        "opportunity": 68.0,
    }]
    first = build_opportunities(rows)
    second = build_opportunities(rows)
    assert first
    assert first[0][0] == second[0][0]
