from __future__ import annotations

from legal_decision_makers import linkedin_profile, merge_leads, normalize_role, parse_result, query_set


def test_linkedin_profile_is_strict():
    assert linkedin_profile("https://www.linkedin.com/in/john-doe/") == "https://www.linkedin.com/in/john-doe"
    assert linkedin_profile("https://linkedin.com/company/acme") == ""
    assert linkedin_profile("https://example.com/in/john") == ""


def test_normalize_role_prefers_highest_decision_weight():
    role, score = normalize_role("Ahmed — CEO & Founder — ACME")
    assert role == "Founder"
    assert score == 100


def test_parse_result_creates_scored_lead():
    lead = parse_result(
        "https://www.linkedin.com/in/ahmed-acme/",
        "Ahmed Mohamed - CEO - ACME Manufacturing | LinkedIn",
        "CEO at ACME Manufacturing in Egypt",
        "CEO",
    )
    assert lead is not None
    assert lead.normalized_role == "CEO"
    assert lead.company == "ACME Manufacturing"
    assert lead.score >= 80
    assert lead.linkedin_url.endswith("/ahmed-acme")


def test_non_profile_results_are_rejected():
    assert parse_result("https://www.linkedin.com/company/acme", "ACME", "", "CEO") is None


def test_query_set_covers_decision_makers_and_industries():
    queries = query_set("Egypt", ["manufacturing"])
    assert len(queries) >= 10
    assert any('"Founder"' in q for q, _ in queries)
    assert any('"manufacturing"' in q for q, _ in queries)


def test_merge_deduplicates_and_preserves_manual_status():
    old = [{"linkedin_url": "https://www.linkedin.com/in/a", "name": "A", "score": 70, "status": "CONTACTED"}]
    new = [{"linkedin_url": "https://www.linkedin.com/in/a", "name": "A Updated", "score": 90, "status": "READY"},
           {"linkedin_url": "https://www.linkedin.com/in/b", "name": "B", "score": 80, "status": "READY"}]
    merged = merge_leads(old, new)
    assert len(merged) == 2
    a = next(x for x in merged if x["linkedin_url"].endswith("/a"))
    assert a["status"] == "CONTACTED"
    assert a["score"] == 90
