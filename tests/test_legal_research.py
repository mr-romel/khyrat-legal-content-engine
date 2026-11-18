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
    assert _allowed("https://www.cairo.gov.eg/ar/Monthly%20Publication/law.pdf")
    assert _allowed("https://sis.gov.eg/media/760267/law-14-2025.pdf")
    assert _allowed("https://media.mof.gov.eg/mof-prd/law.pdf")
    assert not _allowed("https://fake-labour.gov.eg/law.pdf")


def test_any_legal_topic_uses_generic_egyptian_source_discovery(monkeypatch):
    import legal_research

    calls = []
    def fake_search(query):
        calls.append(query)
        return [{"url": "https://moj.gov.eg/laws/intellectual-property", "title": "قانون حماية حقوق الملكية الفكرية"}]

    monkeypatch.setattr(legal_research, "_search", fake_search)
    monkeypatch.setattr(
        legal_research,
        "_fetch",
        lambda url: (
            "قانون حماية حقوق الملكية الفكرية. "
            "تنظم أحكام العلامات التجارية وحقوق المؤلف وبراءات الاختراع. "
            "تسجل العلامات التجارية وفق الإجراءات القانونية المقررة."
        ),
    )
    packet = legal_research.research_legal_topic("الملكية الفكرية والعلامات التجارية — زاوية جديدة: علامات تحذيرية")
    assert legal_research.has_verified_legal_source(packet)
    assert "https://moj.gov.eg/laws/intellectual-property" in packet
    assert "قانون حماية حقوق الملكية الفكرية" in packet
    assert any('"الملكية الفكرية والعلامات التجارية"' in query for query in calls)
    assert not any("قانون العمل 14 لسنة 2025" in query for query in calls)


def test_generic_source_research_does_not_reuse_topic_specific_hardcoded_laws(monkeypatch):
    import legal_research

    monkeypatch.setattr(
        legal_research,
        "_search",
        lambda query: [{"url": "https://moi.gov.eg/laws/inheritance", "title": "قانون المواريث والوصية"}],
    )
    monkeypatch.setattr(
        legal_research,
        "_fetch",
        lambda url: "قانون المواريث ينظم انتقال التركة إلى الورثة وأحكام الوصية والأنصبة الشرعية.",
    )
    packet = legal_research.research_legal_topic("الميراث والوصية")
    assert legal_research.has_verified_legal_source(packet)
    assert "https://moi.gov.eg/laws/inheritance" in packet
    assert "175 لسنة 2018" not in packet
    assert "81 لسنة 2016" not in packet
    assert "14 لسنة 2025" not in packet


def test_topic_evidence_extracts_relevant_passage_from_deep_source_text():
    from legal_research import _source_evidence

    source = (
        "قانون العقوبات رقم 58 لسنة 1937 " + ("مقدمة عامة لا تتعلق بالموضوع " * 300)
        + "في جرائم انتحال الشخصية، المادة (336) يعاقب من استعمل اسماً كاذباً أو صفة غير صحيحة."
    )
    evidence = _source_evidence(source, "انتحال الشخصية")
    assert "قانون رقم 58 لسنة 1937" in evidence
    assert "المادة (336)" in evidence
    assert "مقدمة عامة لا تتعلق" not in evidence


def test_verified_source_url_precedes_retrieved_evidence_in_generic_packet(monkeypatch):
    import legal_research

    monkeypatch.setattr(
        legal_research,
        "_search",
        lambda query: [{"url": "https://moj.gov.eg/laws/test", "title": "قانون الملكية الفكرية"}],
    )
    monkeypatch.setattr(
        legal_research,
        "_fetch",
        lambda url: "قانون الملكية الفكرية ينظم حقوق المؤلف والعلامات التجارية وإجراءات التسجيل.",
    )
    packet = legal_research.research_legal_topic("الملكية الفكرية")
    assert packet.index("URL: https://moj.gov.eg/laws/test") < packet.index("VERIFIED SOURCE TEXT (retrieved):")


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
        + "في جرائم انتحال الشخصية، المادة (336) يعاقب من استعمل اسماً كاذباً أو صفة غير صحيحة."
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



def test_search_result_parser_handles_reordered_html_attributes():
    from legal_research import _SearchResults

    parser = _SearchResults()
    parser.feed(
        '<a href="https://www.caoa.gov.eg/WebForms/laws.aspx" rel="nofollow" class="result__a">قوانين الخدمة المدنية</a>'
        '<a class="result__a" href="https://www.cc.gov.eg/heritage/index-entries">مبادئ محكمة النقض</a>'
    )
    assert len(parser.items) == 2
    assert parser.items[0]["url"].startswith("https://www.caoa.gov.eg/")
    assert parser.items[1]["url"].startswith("https://www.cc.gov.eg/")


def test_official_court_and_public_authority_domains_are_whitelisted():
    from legal_research import _allowed

    assert _allowed("https://www.aca.gov.eg/News/1550.aspx")
    assert _allowed("https://www.sccourt.gov.eg/DjangoPortalResources/Rules_Html/18301_25_115_1_2.html")
    assert not _allowed("https://fake-aca.gov.eg/News/1550.aspx")


def test_official_government_source_can_pass_live_source_gate():
    from legal_research import has_verified_legal_source

    packet = """LEGAL RESEARCH PACKET — VERIFIED WEB SOURCES ONLY
SOURCE 1
Type: official_government_source
Court/source: aca.gov.eg
Title: تنبيه رسمي بشأن انتحال صفة الموظفين العموميين
URL: https://www.aca.gov.eg/News/1550.aspx
VERIFIED SOURCE TEXT (retrieved): تحذر الهيئة من انتحال صفة بعض الموظفين العموميين وتطلب التحقق من هوية الأشخاص والجهات الرسمية.
"""
    assert has_verified_legal_source(packet)



def test_employment_topic_uses_official_civil_service_law_seed(monkeypatch):
    import legal_research

    fetched = []
    monkeypatch.setattr(legal_research, "_search", lambda query: [])
    def fake_fetch(url):
        fetched.append(url)
        return (
            "قانون رقم 81 لسنة 2016 بإصدار قانون الخدمة المدنية. "
            "تسري أحكامه على الوظائف في الوزارات ومصالحها والأجهزة الحكومية. "
            "يكون التعيين في الوظائف العامة وفقاً للقواعد والإجراءات القانونية."
        )
    monkeypatch.setattr(legal_research, "_fetch", fake_fetch)
    packet = legal_research.research_legal_topic(
        "الوظيفة العامة والتعيين — زاوية جديدة: 3 علامات تحذيرية قبل اتخاذ القرار"
    )
    assert any("قانون%20الخدمة%20المدنية" in url for url in fetched)
    assert "https://manshurat.org/node/14678" in fetched
    assert legal_research.has_verified_legal_source(packet)
    assert "SOURCE 1" in packet or "SOURCE 2" in packet
    assert "المادة" in packet


def test_impersonation_topic_uses_official_anti_impersonation_sources(monkeypatch):
    import legal_research

    fetched = []
    monkeypatch.setattr(legal_research, "_search", lambda query: [])
    def fake_fetch(url):
        fetched.append(url)
        return (
            "تحذر هيئة الرقابة الإدارية من انتحال صفة بعض الموظفين العموميين "
            "وضرورة التأكد من هوية الأشخاص والجهات التي يمثلونها. "
            "كما يجرم القانون اتخاذ صفة كاذبة للحصول على منفعة."
        )
    monkeypatch.setattr(legal_research, "_fetch", fake_fetch)
    packet = legal_research.research_legal_topic(
        "انتحال الشخصية — زاوية جديدة: Checklist عملية قبل بدء أي إجراء"
    )
    assert any("aca.gov.eg/News/1550.aspx" in url for url in fetched)
    assert "https://manshurat.org/node/14677" in fetched
    assert legal_research.has_verified_legal_source(packet)
    assert "انتحال صفة" in packet or "صفة رسمية" in packet


def test_topic_evidence_terms_expand_legal_synonyms():
    from legal_research import _topic_evidence_terms

    impersonation = _topic_evidence_terms("انتحال الشخصية")
    employment = _topic_evidence_terms("الوظيفة العامة والتعيين")
    assert "صفة" in impersonation
    assert "الخدمة" in employment
    assert "المدنية" in employment
