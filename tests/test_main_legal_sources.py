from main import _research_and_persist_legal_sources


VERIFIED_PACKET = """LEGAL RESEARCH PACKET — VERIFIED WEB SOURCES ONLY
SOURCE 1
Type: current_legislation_source
Court/source: nosi.gov.eg
Title: قانون الخدمة المدنية رقم 81 لسنة 2016
URL: https://www.nosi.gov.eg/ar/Lists/NOSILibrary/civil-service-law.pdf
VERIFIED SOURCE TEXT (retrieved): المادة (12) يكون التعيين على أساس الكفاءة والجدارة.
"""


def test_live_legal_research_is_retained_when_sheet_persistence_fails(monkeypatch):
    import main

    monkeypatch.setattr(main, "research_legal_topic", lambda topic, existing: VERIFIED_PACKET)

    def fail_update(*args, **kwargs):
        raise RuntimeError("Google Sheets temporary write failure")

    monkeypatch.setattr(main, "update_row", fail_update)
    result = _research_and_persist_legal_sources(
        topic="الوظيفة العامة والتعيين",
        sheet_sources="",
        service=object(),
        config={"sheet_id": "test"},
        sheet_name="Content",
        row_number=12,
    )
    assert result == VERIFIED_PACKET
    from legal_research import has_verified_legal_source
    assert has_verified_legal_source(result)


def test_old_sheet_sources_are_not_reused_when_live_research_raises(monkeypatch):
    import main

    monkeypatch.setattr(
        main,
        "research_legal_topic",
        lambda *args: (_ for _ in ()).throw(RuntimeError("search unavailable")),
    )
    existing = VERIFIED_PACKET
    result = _research_and_persist_legal_sources(
        topic="انتحال الشخصية",
        sheet_sources=existing,
        service=object(),
        config={"sheet_id": "test"},
        sheet_name="Content",
        row_number=13,
    )
    assert result == ""


def test_researched_packet_is_persisted_when_sheet_is_available(monkeypatch):
    import main

    calls = []
    monkeypatch.setattr(main, "research_legal_topic", lambda topic, existing: VERIFIED_PACKET)
    monkeypatch.setattr(main, "update_row", lambda *args, **kwargs: calls.append((args, kwargs)))
    result = _research_and_persist_legal_sources(
        topic="الوظيفة العامة والتعيين",
        sheet_sources="",
        service="service",
        config={"sheet_id": "test"},
        sheet_name="Content",
        row_number=14,
    )
    assert result == VERIFIED_PACKET
    assert len(calls) == 1
    assert calls[0][0][4]["المصادر القانونية"] == VERIFIED_PACKET
