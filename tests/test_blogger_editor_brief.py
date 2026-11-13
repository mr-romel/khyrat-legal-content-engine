from blogger_editor import SYSTEM_PROMPT


def test_blogger_editor_builds_internal_intent_brief_and_outline():
    assert "EDITORIAL CONTENT BRIEF" in SYSTEM_PROMPT
    assert "dominant search intent" in SYSTEM_PROMPT
    assert "logical heading outline" in SYSTEM_PROMPT


def test_blogger_editor_does_not_fabricate_serp_review_or_search_metrics():
    assert "only when SERP results/URLs/snippets are explicitly supplied" in SYSTEM_PROMPT
    assert "do not claim to have reviewed competitors, rankings, search volume" in SYSTEM_PROMPT
