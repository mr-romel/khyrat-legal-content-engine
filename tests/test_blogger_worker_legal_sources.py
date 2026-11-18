from blogger_worker import _refresh_missing_legal_sources


def test_blogger_worker_recovers_missing_legal_sources(monkeypatch):
    import blogger_worker

    packet = """LEGAL RESEARCH PACKET — VERIFIED WEB SOURCES ONLY
SOURCE 1
Type: current_legislation_source
Court/source: media.mof.gov.eg
Title: الجريدة الرسمية — قانون العمل رقم 14 لسنة 2025
URL: https://media.mof.gov.eg/mof-prd/qanwn_aleml_2025_14_f8e36d8b4f.pdf
VERIFIED SOURCE TEXT (retrieved): المادة السادسة ومادة (٢٧) توضح قواعد الترخيص والأحكام الانتقالية في قانون العمل
"""
    calls = []
    monkeypatch.setattr(blogger_worker, "research_legal_topic", lambda topic, existing: calls.append(topic) or packet)
    result = _refresh_missing_legal_sources("ضوابط ترخيص العمالة", "")
    assert result == packet
    assert calls == ["ضوابط ترخيص العمالة"]


def test_blogger_worker_researches_again_even_when_sheet_has_old_verified_source(monkeypatch):
    import blogger_worker

    existing = """SOURCE 1
Type: current_legislation_source
Court/source: media.mof.gov.eg
Title: قانون العمل رقم 14 لسنة 2025
URL: https://media.mof.gov.eg/mof-prd/qanwn_aleml_2025_14_f8e36d8b4f.pdf
VERIFIED SOURCE TEXT (retrieved): نص قانوني مستخرج من ملف الجريدة الرسمية يثبت المصدر والمواد ذات الصلة.
"""
    calls = []
    monkeypatch.setattr(blogger_worker, "research_legal_topic", lambda topic, old: calls.append((topic, old)) or "fresh research packet")
    assert _refresh_missing_legal_sources("ضوابط ترخيص العمالة", existing) == "fresh research packet"
    assert calls == [("ضوابط ترخيص العمالة", existing)]


def test_blogger_worker_does_not_bypass_gate_when_live_research_fails(monkeypatch):
    import blogger_worker

    monkeypatch.setattr(blogger_worker, "research_legal_topic", lambda topic, existing: "No verified sources")
    existing = "No verified sources"
    assert _refresh_missing_legal_sources("ضوابط ترخيص العمالة", existing) == "No verified sources"
    from legal_research import has_verified_legal_source
    assert not has_verified_legal_source(_refresh_missing_legal_sources("ضوابط ترخيص العمالة", existing))
