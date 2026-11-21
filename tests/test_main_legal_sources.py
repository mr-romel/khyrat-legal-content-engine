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


def test_pipeline_attempts_failed_row_once_per_scheduler_cycle(monkeypatch):
    import main

    attempts = []
    updates = []
    states = [{"الحالة": "FAILED", "آخر خطأ": "temporary provider timeout", "الموضوع": "اختبار موضوع قانوني", "آخر تنبيه استرداد": ""}]
    monkeypatch.setattr(main, "_process_row_once", lambda **kwargs: attempts.append(kwargs["row_number"]))
    monkeypatch.setattr(main, "get_values", lambda *args, **kwargs: [[], ["row"]])
    monkeypatch.setattr(main, "row_to_dict", lambda value: states[0])
    monkeypatch.setattr(main, "update_row", lambda *args, **kwargs: updates.append(args[4] if len(args) > 4 else kwargs))
    monkeypatch.setattr(main, "_linkedin_token_blocked", lambda row: False)
    monkeypatch.setattr(main, "_image_qa_attempt_count", lambda row: 0)
    monkeypatch.setattr(main, "notify", lambda message: None)

    main.process_row(
        service=object(), config={"sheet_id": "test", "sheet_range": "Content!A:Y"},
        sheet_name="Content", row_number=2,
        row={"الموضوع": "اختبار موضوع قانوني", "آخر خطأ": "temporary provider timeout", "محاولات الاسترداد": "1"},
        current=__import__("datetime").datetime(2026, 11, 20),
    )

    assert attempts == [2]
    assert any(x.get("محاولات الاسترداد") == "2" for x in updates)


def test_recovery_alert_threshold_is_once_per_failure_signature():
    import main

    error = "LEGAL_SOURCE_GATE_BLOCKED: no verified source"
    assert not main._recovery_alert_required(2, error, "")
    assert main._recovery_alert_required(3, error, "")
    assert not main._recovery_alert_required(4, error, error)
    assert main._recovery_alert_required(3, "different failure", error)



def test_failed_rows_obey_retry_cooldown_and_ready_rows_keep_priority():
    from datetime import datetime, timedelta
    import main

    now = datetime(2026, 11, 21, 12, 0)
    recent = {"الحالة": "FAILED", "الموضوع": "موضوع", "وقت آخر تشغيل": (now - timedelta(minutes=5)).isoformat()}
    eligible = {"الحالة": "FAILED", "الموضوع": "موضوع", "وقت آخر تشغيل": (now - timedelta(minutes=20)).isoformat()}
    assert not main._failed_retry(recent, now)
    assert main._failed_retry(eligible, now)
    import run_main
    assert not run_main._smart_is_due(recent, now)
