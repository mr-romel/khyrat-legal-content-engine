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


def test_ai_module_has_no_submission_automation():
    """The live acquisition/AI module must never log in or submit work automatically."""
    source = open("src/marketplace/live.py", encoding="utf-8").read().lower()
    assert "login" not in source
    assert "logs in" not in source
    assert "submit" not in source
