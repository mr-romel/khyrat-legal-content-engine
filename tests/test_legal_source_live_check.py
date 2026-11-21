from scripts import legal_source_live_check


def test_live_source_check_accepts_arbitrary_semicolon_separated_topics(monkeypatch):
    monkeypatch.setenv(
        "LEGAL_SOURCE_CHECK_TOPICS",
        "ترخيص المحال العامة; التعيين في الوظائف العامة ;ترخيص المحال العامة",
    )
    assert legal_source_live_check.configured_topics() == (
        "ترخيص المحال العامة",
        "التعيين في الوظائف العامة",
    )


def test_live_source_check_defaults_to_all_three_previous_topics(monkeypatch):
    monkeypatch.delenv("LEGAL_SOURCE_CHECK_TOPICS", raising=False)
    assert len(legal_source_live_check.configured_topics()) == 3


def test_live_source_check_all_500_expands_complete_canonical_bank(monkeypatch):
    from topic_bank_500 import TOPIC_BANK

    monkeypatch.setenv("LEGAL_SOURCE_CHECK_TOPICS", "ALL_500")
    topics = legal_source_live_check.configured_topics()
    assert len(topics) == 500
    assert len(set(topics)) == 500
    assert topics[0] == TOPIC_BANK[0]["topic"]
