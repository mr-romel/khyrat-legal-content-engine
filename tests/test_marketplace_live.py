from marketplace.live import LEGAL_TERMS, score_legal_relevance


def test_legal_relevance_prefers_contract_and_law_projects():
    score, reasons = score_legal_relevance(
        "مطلوب محامي لمراجعة عقد شراكة",
        "مراجعة البنود وصياغة التعديلات القانونية وحماية حقوق الشركاء",
    )
    assert score >= 45
    assert reasons


def test_non_legal_project_is_not_marked_as_legal():
    score, reasons = score_legal_relevance(
        "مطلوب مصمم لوجو",
        "تصميم شعار وهوية بصرية لمطعم",
    )
    assert score < 45
    assert "عقد" in LEGAL_TERMS


def test_live_module_has_no_submission_automation():
    """Live acquisition must only discover opportunities; submission stays manual."""
    source = open("src/marketplace/live.py", encoding="utf-8").read().lower()
    forbidden = (
        "login",
        "logs in",
        "session.post",
        "submit_project",
        "submit proposal",
        "auto-submit",
        "autosubmit",
    )
    assert not any(marker in source for marker in forbidden)


def test_live_module_only_fetches_public_marketplace_data():
    source = open("src/marketplace/live.py", encoding="utf-8").read().lower()
    assert "mostaql.com/projects" in source
    assert "requests.session" in source
    assert "fetch_mostaql_projects" in source
