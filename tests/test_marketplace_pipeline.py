from marketplace.catalog import prioritized_topics
from marketplace.pipeline import ensure_initial_assets, offer_quality, ingest_mostaql_opportunity, summarize_pipeline


def test_initial_assets_are_idempotent():
    state = {"services": [], "portfolio": [], "opportunities": [], "activity": []}
    first = ensure_initial_assets(state)
    second = ensure_initial_assets(state)
    assert first["services_created"] == len(prioritized_topics())
    assert first["portfolio_created"] == 4
    assert second["services_created"] == 0
    assert second["portfolio_created"] == 0


def test_mostaql_ingestion_builds_offer_and_quality_passes():
    state = {"services": [], "portfolio": [], "opportunities": [], "activity": []}
    item = ingest_mostaql_opportunity(
        state,
        "مطلوب محامي لمراجعة عقد شركة",
        "مراجعة عقد شركة وتحديد المخاطر واقتراح تعديلات وصياغة البنود القانونية",
    )
    assert item["offer"]
    assert item["status"] == "OFFER_READY"
    result = offer_quality(item)
    assert result["passed"] is True


def test_mostaql_opportunity_keeps_direct_source_link():
    state = {"services": [], "portfolio": [], "opportunities": [], "activity": []}
    item = ingest_mostaql_opportunity(
        state,
        "مطلوب مراجعة عقد",
        "مراجعة عقد تجاري وتحديد المخاطر والبنود المطلوب تعديلها",
        "https://mostaql.com/project/123456",
    )
    assert item["source_url"] == "https://mostaql.com/project/123456"


def test_mostaql_opportunity_rejects_unsafe_source_link():
    state = {"services": [], "portfolio": [], "opportunities": [], "activity": []}
    try:
        ingest_mostaql_opportunity(
            state,
            "مطلوب مراجعة عقد",
            "مراجعة عقد تجاري وتحديد المخاطر والبنود المطلوب تعديلها",
            "javascript:alert(1)",
        )
    except ValueError as exc:
        assert "http://" in str(exc) or "https://" in str(exc)
    else:
        raise AssertionError("unsafe source URL should be rejected")


def test_quality_rejects_external_links():
    result = offer_quality(
        {
            "platform": "mostaql",
            "offer": "المدة المقترحة: 2 أيام. الميزانية المقترحة: 1500 جنيه. نطاق العمل: مراجعة المستند. https://example.com",
        }
    )
    assert result["passed"] is False
    assert "العرض يحتوي على رابط خارجي" in result["issues"]


def test_summary_reports_pipeline_state():
    state = {"services": [{"id": "1"}], "portfolio": [{"id": "2"}], "opportunities": [{"match_score": 80, "status": "OFFER_READY", "offer": "x"}], "activity": []}
    summary = summarize_pipeline(state)
    assert summary["services"] == 1
    assert summary["portfolio"] == 1
    assert summary["opportunities"] == 1
    assert summary["ready_offers"] == 1
