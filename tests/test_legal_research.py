from legal_research import _case, _date, _effective, _quote, validate_legal_citations

def test_extract_case_number():
    text = "محكمة النقض — الطعن رقم 7294 لسنة 95 قضائية — جلسة 02/05/2026"
    assert _case(text) == "7294 لسنة 95 قضائية"

def test_extract_date():
    text = "الطعن رقم 7294 لسنة 95 قضائية جلسة 02/05/2026"
    assert _date(text) == "02/05/2026"

def test_extract_effective_date_text():
    text = "وينشر القانون ويعمل به من أول أكتوبر التالي لتاريخ نشره"
    assert "أول أكتوبر" in _effective(text)

def test_quote_is_source_only_and_short():
    source = "هذه جملة من الحكم مرتبطة مباشرة بالموضوع. وهذه جملة ثانية لا نحتاجها."
    quote = _quote(source, "الموضوع")
    assert quote
    assert len(quote.split()) <= 24



def test_blocks_invented_egyptian_general_administration_law():
    post = "المادة 6 من قانون الإدارة العامة بتلزم الإدارة إن التفويض يبقى مكتوب"
    issues = validate_legal_citations(post, "LEGAL RESEARCH PACKET — no verified source retrieved.")
    assert any("قانون الإدارة العامة" in issue for issue in issues)


def test_blocks_unverified_article_even_if_present_in_user_notes():
    post = "المادة 6 من قانون رقم 42 لسنة 1967 تنظم التفويض"
    packet = (
        "LEGAL RESEARCH PACKET — VERIFIED WEB SOURCES ONLY\n"
        "No sufficiently verified source retrieved.\n"
        "EXISTING SHEET LEGAL SOURCES:\n"
        "المادة 6 من قانون رقم 42 لسنة 1967"
    )
    issues = validate_legal_citations(post, packet)
    assert issues


def test_accepts_precise_citation_present_in_retrieved_evidence():
    post = "المادة 6 من قانون رقم 42 لسنة 1967 تنظم التفويض"
    packet = (
        "SOURCE 1\n"
        "VERIFIED SOURCE TEXT (retrieved): المادة 6 من قانون رقم 42 لسنة 1967 بشأن التفويض في الاختصاصات"
    )
    assert validate_legal_citations(post, packet) == []


def test_blocks_unverified_court_case_and_session_date():
    post = "قضت المحكمة الإدارية العليا في الطعن رقم 25096 لسنة 55 قضائية بجلسة 22/04/2015"
    issues = validate_legal_citations(post, "No verified court record retrieved.")
    assert len(issues) >= 2


def test_accepts_law_number_when_official_source_uses_definite_article():
    post = "الجرائم الإلكترونية وفق قانون رقم 175 لسنة 2018"
    packet = (
        "SOURCE 1\n"
        "VERIFIED SOURCE TEXT (retrieved): القانون رقم ١٧٥ لسنة ٢٠١٨ في شأن مكافحة جرائم تقنية المعلومات"
    )
    assert validate_legal_citations(post, packet) == []



def test_official_egyptian_legislation_portal_is_allowed_but_arbitrary_domain_is_not():
    from legal_research import _allowed

    assert _allowed("https://elpai.idsc.gov.eg/GeneralSearch/LegalDatabases?tab=legislation")
    assert _allowed("https://mof.gov.eg/ar/legislation/legislation")
    assert not _allowed("https://example.com/egypt-law")
    assert not _allowed("http://elpai.idsc.gov.eg/GeneralSearch/LegalDatabases")



def test_verified_legal_source_gate_requires_whitelisted_https_source_block():
    from legal_research import has_verified_legal_source

    packet = """LEGAL RESEARCH PACKET — VERIFIED WEB SOURCES ONLY
SOURCE 1
Type: current_legislation_source
Court/source: elpai.idsc.gov.eg
Title: بوابة التشريعات المصرية
URL: https://elpai.idsc.gov.eg/GeneralSearch/LegalDatabases?tab=legislation
VERIFIED SOURCE TEXT (retrieved): نص تشريعي رسمي تم جلبه والتحقق من محتواه الفعلي.
"""
    assert has_verified_legal_source(packet)
    assert not has_verified_legal_source("LEGAL RESEARCH PACKET: no sufficiently verified sources")
    bad = packet.replace("https://elpai.idsc.gov.eg", "https://example.com")
    assert not has_verified_legal_source(bad)

def test_official_labour_and_state_information_subdomains_are_allowed():
    from legal_research import _allowed

    assert _allowed("https://www.labour.gov.eg/laws-and-legislations/")
    assert _allowed("https://sis.gov.eg/media/760267/law-14-2025.pdf")
    assert _allowed("https://media.mof.gov.eg/mof-prd/law.pdf")
    assert not _allowed("https://fake-labour.gov.eg/law.pdf")


def test_employment_topic_injects_verified_primary_law_sources(monkeypatch):
    import legal_research

    monkeypatch.setattr(legal_research, "_fetch", lambda url: "قانون رقم 14 لسنة 2025 قانون العمل، نص تشريعي رسمي مستخرج من الجريدة الرسمية ويتضمن الأحكام القانونية ذات الصلة بالموضوع.")
    monkeypatch.setattr(legal_research, "_search", lambda query: [])
    packet = legal_research.research_legal_topic("ضوابط ترخيص العمالة ومخاطر التشغيل دون ترخيص قانوني")
    assert "https://media.mof.gov.eg/mof-prd/qanwn_aleml_2025_14_f8e36d8b4f.pdf" in packet
    assert "https://sis.gov.eg/media/760267/" in packet
    assert "قانون العمل رقم 14 لسنة 2025" in packet
    assert legal_research.has_verified_legal_source(packet)

def test_employment_source_evidence_extracts_relevant_late_articles():
    from legal_research import _source_evidence

    source = (
        ("مقدمة عامة لا تتعلق بالترخيص " * 1800)
        + "المادة السادسة يجوز لأصحاب الأعمال تشغيل العمال دون التقيد بشرط الترخيص وتوفيق الأوضاع خلال ثلاث سنوات. "
        + "مادة (٢٧): يلتزم من يرغب في مزاولة مهنة أو حرفة بالحصول على ترخيص. "
        + "مادة (٢٩١): يعاقب من يزاول عمليات إلحاق العمالة دون ترخيص."
    )
    evidence = _source_evidence(source, "ضوابط ترخيص العمالة ومخاطر التشغيل دون ترخيص قانوني")
    assert "المادة السادسة" in evidence
    assert "مادة (٢٧)" in evidence
    assert "مادة (٢٩١)" in evidence
    assert "مقدمة عامة لا تتعلق" not in evidence


def test_verified_source_url_precedes_long_evidence_in_packet():
    import legal_research

    monkeypatch = __import__("pytest").MonkeyPatch()
    try:
        monkeypatch.setattr(legal_research, "_fetch", lambda url: "مادة (٢٧): ترخيص المهنة")
        monkeypatch.setattr(legal_research, "_search", lambda query: [])
        packet = legal_research.research_legal_topic("ضوابط ترخيص العمالة")
        assert packet.index("URL: https://media.mof.gov.eg/") < packet.index("VERIFIED SOURCE TEXT (retrieved):")
    finally:
        monkeypatch.undo()


def test_public_service_topic_injects_civil_service_law_and_extracts_appointment_articles(monkeypatch):
    import legal_research

    def fake_fetch(url):
        if "nosi.gov.eg" in url:
            return (
                "قانون رقم 81 لسنة 2016 بشأن الخدمة المدنية. "
                "المادة (12) يكون التعيين بموجب قرار على أساس الكفاءة والجدارة من خلال إعلان مركزي وامتحان. "
                "المادة (14) يشترط فيمن يعين استيفاء شروط شغل الوظيفة واجتياز الامتحان."
            )
        return "اللائحة التنفيذية لقانون الخدمة المدنية رقم 1216 لسنة 2017"
    monkeypatch.setattr(legal_research, "_fetch", fake_fetch)
    monkeypatch.setattr(legal_research, "_search", lambda query: [])

    packet = legal_research.research_legal_topic("الوظيفة العامة والتعيين")
    assert "قانون الخدمة المدنية رقم 81 لسنة 2016" in packet
    assert "https://www.nosi.gov.eg/" in packet
    assert "المادة (12)" in packet
    assert "المادة (14)" in packet
    assert legal_research.has_verified_legal_source(packet)


def test_impersonation_topic_injects_cybercrime_and_penal_code_sources(monkeypatch):
    import legal_research

    def fake_fetch(url):
        if "fra.gov.eg" in url:
            return (
                "القانون رقم 175 لسنة 2018. "
                "المادة (24) يعاقب كل من اصطنع حساباً خاصاً ونسبه زوراً إلى شخص طبيعي."
            )
        return (
            "قانون العقوبات رقم 58 لسنة 1937. "
            "المادة (155) كل من تداخل في وظيفة عمومية دون صفة رسمية يعاقب. "
            "المادة (336) يعاقب من استعمل اسماً كاذباً أو صفة غير صحيحة."
        )
    monkeypatch.setattr(legal_research, "_fetch", fake_fetch)
    monkeypatch.setattr(legal_research, "_search", lambda query: [])

    packet = legal_research.research_legal_topic("انتحال الشخصية")
    assert "قانون رقم 175 لسنة 2018" in packet
    assert "https://fra.gov.eg/" in packet
    assert "https://manshurat.org/node/14677" in packet
    assert "المادة (24)" in packet
    assert "المادة (155)" in packet
    assert legal_research.has_verified_legal_source(packet)


def test_civil_service_authority_is_whitelisted_but_lookalike_is_not():
    from legal_research import _allowed

    assert _allowed("https://www.nosi.gov.eg/law.pdf")
    assert _allowed("https://www.caoa.gov.eg/WebForms/laws.aspx")
    assert _allowed("https://fra.gov.eg/law.pdf")
    assert not _allowed("https://fake-caoa.gov.eg/law.pdf")


def test_official_and_secondary_sources_use_topic_relevant_evidence(monkeypatch):
    import legal_research

    monkeypatch.setattr(
        legal_research,
        "_fetch",
        lambda url: ("مقدمة طويلة لا تتعلق بالموضوع " * 500)
        + "المادة (24) انتحال حساب ونسبته إلى شخص طبيعي.",
    )
    monkeypatch.setattr(legal_research, "_search", lambda query: [])
    packet = legal_research.research_legal_topic("انتحال الشخصية")
    assert "المادة (24)" in packet
    assert "مقدمة طويلة" not in packet


def test_source_gate_rejects_whitelisted_url_without_retrieved_source_text():
    from legal_research import has_verified_legal_source

    packet = """SOURCE 1
Type: current_legislation_source
Court/source: nosi.gov.eg
Title: قانون الخدمة المدنية
URL: https://www.nosi.gov.eg/law.pdf
"""
    assert not has_verified_legal_source(packet)


def test_topic_evidence_keeps_law_number_when_article_is_deep_in_document():
    from legal_research import _source_evidence

    source = (
        "قانون العقوبات رقم 58 لسنة 1937 " + ("مقدمة عامة لا تتعلق بالموضوع " * 300)
        + "المادة (336) يعاقب من استعمل اسماً كاذباً أو صفة غير صحيحة."
    )
    evidence = _source_evidence(source, "انتحال الشخصية")
    assert "قانون رقم 58 لسنة 1937" in evidence
    assert "المادة (336)" in evidence


def test_live_source_gate_ignores_old_sources_in_sheet_reference_section():
    from legal_research import has_verified_legal_source

    packet = """LEGAL RESEARCH PACKET — VERIFIED WEB SOURCES ONLY
Research date: 2026-11-18
No sufficiently verified topic-specific court/legislation source was retrieved automatically.
EXISTING SHEET LEGAL SOURCES:
SOURCE 1
Type: current_legislation_source
Court/source: nosi.gov.eg
Title: Old Civil Service Law source
URL: https://www.nosi.gov.eg/old-law.pdf
VERIFIED SOURCE TEXT (retrieved): Previously retrieved statutory text that is no longer verified in this run.
"""
    assert not has_verified_legal_source(packet)
