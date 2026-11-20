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
        "Type: current_legislation_source\n"
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
        "Type: current_legislation_source\n"
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
    assert any("jobs.caoa.gov.eg" in url for url in fetched)
    assert not any("manshurat.org/node/14678" in url for url in fetched)
    assert "https://lawhub.info/eg/?p=11478" not in packet
    assert legal_research.has_verified_legal_source(packet)
    assert "SOURCE 1" in packet
    assert "التعيين" in packet


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


def test_negative_administrative_decision_fails_closed_when_live_research_fails(monkeypatch):
    import legal_research

    monkeypatch.setattr(legal_research, "_search", lambda _query: [])
    monkeypatch.setattr(legal_research, "_fetch", lambda _url: "")
    packet = legal_research.research_legal_topic("امتناع الإدارة عن اتخاذ القرار")
    assert not legal_research.has_verified_legal_source(packet)
    assert "VERIFIED SOURCE TEXT (retrieved):" not in packet
    assert "21855 لسنة 65 قضائية" not in packet
    assert "https://manshurat.org/sites/default/files/docs/pdf/009589.pdf" not in packet
    assert legal_research.validate_legal_citations(
        "القرار السلبي وفق المادة 10 من قانون رقم 47 لسنة 1972",
        packet,
    )


def test_civil_service_appointment_fails_closed_when_live_primary_sources_fail(monkeypatch):
    import legal_research

    monkeypatch.setattr(legal_research, "_search", lambda _query: [])
    monkeypatch.setattr(legal_research, "_fetch", lambda _url: "")
    packet = legal_research.research_legal_topic("الوظيفة العامة والتعيين")
    assert not legal_research.has_verified_legal_source(packet)
    assert "VERIFIED SOURCE TEXT (retrieved):" not in packet
    assert "https://lawhub.info/eg/?p=11478" not in packet
    assert legal_research.validate_legal_citations(
        "التعيين وفق المادة 12 من قانون رقم 81 لسنة 2016",
        packet,
    )


def test_secondary_legal_reference_cannot_satisfy_primary_source_gate():
    from legal_research import has_verified_legal_source

    packet = """SOURCE 1
Type: secondary_legislation_reference
Court/source: legal database
Title: Civil Service Law No. 81 of 2016
URL: https://lawhub.info/eg/?p=11478
VERIFIED SOURCE TEXT (retrieved): المادة 12 من قانون رقم 81 لسنة 2016 تنظم التعيين بموجب الكفاءة والجدارة.
"""
    assert not has_verified_legal_source(packet)


def test_secondary_legal_reference_cannot_verify_precise_statutory_citation():
    post = "المادة 12 من قانون رقم 81 لسنة 2016 تنظم التعيين"
    packet = """SOURCE 1
Type: secondary_legislation_reference
Court/source: legal database
Title: Civil Service Law No. 81 of 2016
URL: https://lawhub.info/eg/?p=11478
VERIFIED SOURCE TEXT (retrieved): المادة 12 من قانون رقم 81 لسنة 2016 تنظم التعيين بموجب الكفاءة والجدارة.
"""
    assert validate_legal_citations(post, packet)


def test_untyped_source_block_cannot_verify_precise_legal_citation():
    post = "المادة 12 من قانون رقم 81 لسنة 2016 تنظم التعيين"
    packet = """SOURCE 1
Title: Unclassified source
URL: https://moj.gov.eg/laws/example
VERIFIED SOURCE TEXT (retrieved): المادة 12 من قانون رقم 81 لسنة 2016 تنظم التعيين.
"""
    assert validate_legal_citations(post, packet)


def test_negative_administrative_decision_discovers_official_state_council_source(monkeypatch):
    import legal_research

    fetched = []
    monkeypatch.setattr(legal_research, "_search", lambda _query: [])

    def fake_fetch(url):
        fetched.append(url)
        if "esc.gov.eg/service/" in url:
            return (
                "القسم القضائي بمجلس الدولة المصري. تختص محاكم مجلس الدولة دون غيرها بالفصل "
                "في المنازعات الإدارية. ويعتبر في حكم القرارات الإدارية رفض السلطات الإدارية "
                "أو امتناعها عن اتخاذ قرار كان من الواجب عليها اتخاذه وفقا للقوانين واللوائح."
            )
        if "mof.gov.eg/ar/legislation/legislation-5fe86ada" in url:
            return "قانون رقم 47 لسنة 1972 بشأن مجلس الدولة. حالة القانون: سارٍ."
        return ""

    monkeypatch.setattr(legal_research, "_fetch", fake_fetch)
    packet = legal_research.research_legal_topic("امتناع الإدارة عن اتخاذ القرار")

    assert any("esc.gov.eg/service/" in url for url in fetched)
    assert legal_research.has_verified_legal_source(packet)
    assert "امتناعها عن اتخاذ قرار" in packet
    assert "Type: official_government_source" in packet
    assert legal_research.validate_legal_citations("قانون رقم 47 لسنة 1972", packet)


def test_state_council_law_status_page_alone_does_not_verify_negative_decision(monkeypatch):
    import legal_research

    monkeypatch.setattr(legal_research, "_search", lambda _query: [])
    monkeypatch.setattr(
        legal_research,
        "_fetch",
        lambda _url: "قانون رقم 47 لسنة 1972 بشأن مجلس الدولة. حالة القانون: سارٍ.",
    )
    packet = legal_research.research_legal_topic("امتناع الإدارة عن اتخاذ القرار")
    assert not legal_research.has_verified_legal_source(packet)
    assert "رفض السلطات الإدارية" not in packet


def test_ministry_law_status_page_cannot_satisfy_substantive_legal_source_gate(monkeypatch):
    import legal_research

    monkeypatch.setattr(legal_research, "_search", lambda _query: [])
    def fake_fetch(url):
        if "esc.gov.eg" in url:
            return ""
        return (
            "قانون رقم 47 لسنة 1972 بشأن مجلس الدولة. حالة القانون: سارٍ. "
            "ويعتبر في حكم القرارات الإدارية رفض السلطات الإدارية أو امتناعها "
            "عن اتخاذ قرار كان من الواجب عليها اتخاذه وفقا للقوانين واللوائح."
        )

    monkeypatch.setattr(legal_research, "_fetch", fake_fetch)
    packet = legal_research.research_legal_topic("امتناع الإدارة عن اتخاذ القرار")
    assert "Type: legislation_status_source" in packet
    assert not legal_research.has_verified_legal_source(packet)


def test_trusted_http_fetch_retries_with_os_ca_bundle_without_disabling_tls(monkeypatch):
    import requests
    import legal_research

    calls = []
    response = type("Response", (), {"status_code": 200})()

    def fake_get(url, **kwargs):
        calls.append(kwargs.copy())
        if len(calls) == 1:
            raise requests.exceptions.SSLError("certifi CA failure")
        return response

    monkeypatch.setattr(legal_research.requests, "get", fake_get)
    monkeypatch.setenv("SSL_CERT_FILE", "")
    monkeypatch.setattr(legal_research.os.path, "isfile", lambda _path: True)
    result = legal_research._trusted_get("https://official.gov.eg/source", timeout=3)

    assert result is response
    assert len(calls) == 2
    assert calls[1]["verify"] == "/etc/ssl/certs/ca-certificates.crt"
    assert calls[1]["verify"] is not False


def test_official_constitutional_court_source_supports_merit_in_public_appointment(monkeypatch):
    import legal_research

    fetched = []
    monkeypatch.setattr(legal_research, "_search", lambda _query: [])

    def fake_fetch(url):
        fetched.append(url)
        if "sccourt.gov.eg/DjangoPortalResources/Rules_Html/10425_" in url:
            return (
                "حكم المحكمة الدستورية العليا. وكان المشرع قد ألغى قانون نظام العاملين المدنيين بالدولة "
                "بموجب قانون الخدمة المدنية رقم 81 لسنة 2016. ولا يجوز أن يكون التعيين في وظيفة بذاتها "
                "عملا آليا يفتقر إلى الأسس الموضوعية أو منفصلا عن عوامل الخبرة والجدارة التي يتم على "
                "ضوئها اختيار من يتولاها."
            )
        return ""

    monkeypatch.setattr(legal_research, "_fetch", fake_fetch)
    packet = legal_research.research_legal_topic("الوظيفة العامة والتعيين")

    assert any("sccourt.gov.eg/DjangoPortalResources/Rules_Html/10425_" in url for url in fetched)
    assert legal_research.has_verified_legal_source(packet)
    assert "Type: judgment_or_principle" in packet
    assert "الخبرة والجدارة" in packet


def test_accessible_aca_source_supports_civil_service_and_appointment_context(monkeypatch):
    import legal_research

    fetched = []
    monkeypatch.setattr(legal_research, "_search", lambda _query: [])

    def fake_fetch(url):
        fetched.append(url)
        if "aca.gov.eg/News/1625.aspx" in url:
            return (
                "الإطار التشريعي. قانون الخدمة المدنية رقم 81 لسنة 2016. "
                "هو القانون المستحدث المعني بالعاملين بالجهاز الإداري للدولة من حيث تنظيم طرق "
                "التعيين وترتيب وتوصيف وتقييم الوظائف ونقل العاملين وترقياتهم."
            )
        return ""

    monkeypatch.setattr(legal_research, "_fetch", fake_fetch)
    packet = legal_research.research_legal_topic("الوظيفة العامة والتعيين")

    assert any("aca.gov.eg/News/1625.aspx" in url for url in fetched)
    assert legal_research.has_verified_legal_source(packet)
    assert "Type: official_government_source" in packet
    assert legal_research.validate_legal_citations(
        "قانون رقم 81 لسنة 2016",
        packet,
    ) == []
    assert legal_research.validate_legal_citations(
        "المادة 12 من قانون رقم 81 لسنة 2016",
        packet,
    )


def test_official_caoa_jobs_portal_supports_civil_service_appointment_context(monkeypatch):
    import legal_research

    fetched = []
    monkeypatch.setattr(legal_research, "_search", lambda _query: [])

    def fake_fetch(url):
        fetched.append(url)
        if url.rstrip("/") == "https://jobs.caoa.gov.eg":
            return (
                "بوابة الوظائف الحكومية. الوظائف المتاحة: وظائف تشغل بالتعيين والتعاقد. "
                "مكتبة الموقع: قانون الخدمة المدنية رقم 81 لسنة 2016 واللائحة التنفيذية. "
                "تعلن الجهات الحكومية عن الوظائف الشاغرة وشروط شغلها."
            )
        if "caoa.gov.eg/WebForms/laws.aspx" in url:
            return "الجهاز المركزي للتنظيم والإدارة. قوانين ومبادئ مستقرة. قانون الخدمة المدنية 2016 رقم 81."
        return ""

    monkeypatch.setattr(legal_research, "_fetch", fake_fetch)
    packet = legal_research.research_legal_topic("الوظيفة العامة والتعيين")

    assert any("jobs.caoa.gov.eg" in url for url in fetched)
    assert legal_research.has_verified_legal_source(packet)
    assert "Type: official_government_source" in packet
    assert legal_research.validate_legal_citations(
        "قانون رقم 81 لسنة 2016",
        packet,
    ) == []
    assert legal_research.validate_legal_citations(
        "المادة 12 من قانون رقم 81 لسنة 2016",
        packet,
    )

def test_privacy_topic_recovers_official_primary_sources_when_live_search_is_unavailable(monkeypatch):
    import legal_research

    fetched = []
    monkeypatch.setattr(legal_research, "_search", lambda _query: [])

    def fake_fetch(url):
        fetched.append(url)
        if "fra.gov.eg/wp-content/uploads/2025/01/" in url:
            return (
                "الجريدة الرسمية. القانون رقم 175 لسنة 2018 بشأن مكافحة جرائم تقنية المعلومات. "
                "الفصل الثالث الجرائم المتعلقة بالاعتداء على حرمة الحياة الخاصة. "
                "المادة (25) يعاقب كل من انتهك حرمة الحياة الخاصة أو نشر معلومات أو صوراً "
                "تنتهك خصوصية أي شخص دون رضاه سواء كانت المعلومات صحيحة أو غير صحيحة."
            )
        if "escc.gov.eg/assets/docs/law-175-2018.pdf" in url:
            return (
                "القانون رقم 175 لسنة 2018 بشأن مكافحة جرائم تقنية المعلومات. "
                "الفصل الثالث الجرائم المتعلقة بالاعتداء على حرمة الحياة الخاصة. "
                "المادة (25) يعاقب كل من انتهك حرمة الحياة الخاصة أو نشر معلومات أو صوراً "
                "تنتهك خصوصية أي شخص دون رضاه سواء كانت المعلومات صحيحة أو غير صحيحة."
            )
        if "register.cc.gov.eg/publications/159/download" in url:
            return (
                "محكمة النقض المصرية. جريمة الاعتداء على حرمة الحياة الخاصة وفقاً للمادة 309 مكرراً "
                "عقوبات تتحقق بالتقاط صورة شخص في مكان خاص دون رضائه."
            )
        return ""

    monkeypatch.setattr(legal_research, "_fetch", fake_fetch)
    packet = legal_research.research_legal_topic(
        "انتهاك حرمة الحياة الخاصة — زاوية جديدة: Checklist عملية قبل بدء أي إجراء"
    )

    assert any("fra.gov.eg/wp-content/uploads/2025/01/" in url for url in fetched)
    assert "https://escc.gov.eg/assets/docs/law-175-2018.pdf" in fetched
    assert legal_research.has_verified_legal_source(packet)
    assert "قانون رقم 175 لسنة 2018" in packet
    assert "المادة 25" in packet
    assert "انتهك حرمة الحياة الخاصة" in packet



def test_bing_result_parser_handles_organic_result_containers():
    from legal_research import _BingResults

    parser = _BingResults()
    parser.feed(
        '<ol><li class="b_algo"><h2><a href="https://www.moj.gov.eg/law">نص القانون الرسمي</a></h2>'
        '<p>ملخص</p></li></ol>'
    )
    assert parser.items == [{"url": "https://www.moj.gov.eg/law", "title": "نص القانون الرسمي"}]


def test_search_falls_back_to_bing_when_duckduckgo_has_no_parseable_results(monkeypatch):
    import legal_research

    class Response:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code
        def raise_for_status(self):
            return None

    calls = []
    def fake_get(url, **kwargs):
        calls.append(url)
        if "duckduckgo" in url:
            return Response("<html><body>challenge page</body></html>")
        return Response(
            '<li class="b_algo"><h2><a href="https://www.moj.gov.eg/laws/1">مصدر تشريعي رسمي</a></h2></li>'
        )

    monkeypatch.setattr(legal_research, "_trusted_get", fake_get)
    results = legal_research._search("اختبار بحث قانوني")
    assert len(results) == 1
    assert results[0]["url"] == "https://www.moj.gov.eg/laws/1"
    assert calls == ["https://html.duckduckgo.com/html/", "https://www.bing.com/search"]


def test_fetch_retries_once_after_transient_connection_error(monkeypatch):
    import legal_research
    import requests

    class Response:
        status_code = 200
        headers = {"content-type": "text/html"}
        text = "<html><body>نص قانوني رسمي كامل</body></html>"
        def raise_for_status(self):
            return None

    calls = {"count": 0}
    def fake_get(url, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise requests.exceptions.ConnectionError("temporary reset")
        return Response()

    monkeypatch.setattr(legal_research, "_trusted_get", fake_get)
    monkeypatch.setattr(legal_research.time, "sleep", lambda seconds: None)
    assert "نص قانوني رسمي كامل" in legal_research._fetch("https://www.moj.gov.eg/law")
    assert calls["count"] == 2


def test_generic_query_reformulations_apply_to_unlisted_legal_topics(monkeypatch):
    import legal_research

    captured = []
    monkeypatch.setattr(legal_research, "_search", lambda query: captured.append(query) or [])
    monkeypatch.setattr(legal_research, "_fetch", lambda _url: "")
    legal_research.research_legal_topic("تنظيم تراخيص المحال العامة")

    assert len(captured) >= 16
    assert any('"تنظيم تراخيص المحال العامة" مصر قانون تشريع' in query for query in captured)
    assert any("site:gov.eg" in query for query in captured)
    assert any("قرار إداري لائحة" in query for query in captured)


def test_cached_official_source_is_refetched_and_revalidated_for_current_topic(monkeypatch):
    import legal_research

    cached_url = "https://www.nosi.gov.eg/ar/Lists/NOSILibrary/legal-reference.pdf"
    existing = (
        "LEGAL RESEARCH PACKET — VERIFIED WEB SOURCES ONLY\n"
        "SOURCE 1\nType: current_legislation_source\n"
        "Title: مرجع قانوني سابق\nURL: " + cached_url + "\n"
        "VERIFIED SOURCE TEXT (retrieved): نص سابق\n"
    )
    fetched = []
    monkeypatch.setattr(legal_research, "_search", lambda query: [])
    monkeypatch.setattr(
        legal_research,
        "_fetch",
        lambda url: fetched.append(url) or (
            "تنظيم تراخيص المحال العامة وفق المادة 12 من القانون رقم 1 لسنة 2020. "
            "ويحدد النص الشروط والإجراءات والاختصاصات القانونية ذات الصلة."
        ),
    )

    legal_research.research_legal_topic("تنظيم تراخيص المحال العامة", existing)

    assert cached_url in fetched


def test_public_employment_topic_includes_official_law_81_terms_and_source_domain():
    import legal_research

    terms = legal_research._topic_evidence_terms("الوظيفة العامة والتعيين")
    assert "الوظائف" in terms
    assert legal_research._allowed(
        "https://www.mwri.gov.eg/wp-content/uploads/2019/12/Civil-Service-Law.pdf"
    )
    evidence = legal_research._source_evidence(
        "قانون الخدمة المدنية. الوظائف المدنية حق للمواطنين على أساس الكفاءة والجدارة.",
        "الوظيفة العامة والتعيين",
    )
    assert "الوظائف المدنية" in evidence


def test_official_host_allowlist_normalizes_www_case_and_subdomains():
    import legal_research

    assert legal_research._allowed("https://www.mwri.gov.eg/law.pdf")
    assert legal_research._allowed("https://files.mwri.gov.eg/law.pdf")
    assert legal_research._allowed("https://WWW.FRA.GOV.EG/law.pdf")
    assert not legal_research._allowed("http://www.mwri.gov.eg/law.pdf")
    assert not legal_research._allowed("https://mwri.gov.eg.example.com/law.pdf")


def test_pdf_fetch_uses_arabic_layout_text_when_plain_extraction_is_garbled(monkeypatch):
    import sys
    from types import SimpleNamespace
    import legal_research

    class FakePage:
        def extract_text(self, extraction_mode=None):
            if extraction_mode == "layout":
                return "الوظائف المدنية حق للمواطنين على أساس الكفاءة والجدارة"
            return "garbled"

    class FakeReader:
        def __init__(self, _stream):
            self.pages = [FakePage()]

    response = SimpleNamespace(
        status_code=200,
        headers={"content-type": "application/pdf"},
        content=b"%PDF-test",
        raise_for_status=lambda: None,
    )
    monkeypatch.setattr(legal_research, "_trusted_get", lambda *args, **kwargs: response)
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))

    extracted = legal_research._fetch("https://www.moa.gov.eg/law.pdf")

    assert "الوظائف المدنية" in extracted
    assert "الكفاءة والجدارة" in extracted


def test_cairo_government_publication_is_allowlisted_for_civil_service_law():
    import legal_research

    assert legal_research._allowed(
        "https://www.cairo.gov.eg/ar/Monthly%20Publication/%D9%86%D8%B4%D8%B1%D8%A9%20%D9%81%D8%A8%D8%B1%D8%A7%D9%8A%D8%B12019%20.pdf"
    )
    terms = legal_research._topic_evidence_terms("الوظيفة العامة والتعيين")
    assert "الوظائف" in terms
    assert "الكفاءة" in terms
    assert "الجدارة" in terms


def test_pdf_extraction_falls_back_to_arabic_ocr_when_native_text_is_unusable(monkeypatch):
    import legal_research

    class FakePage:
        def extract_text(self, extraction_mode=None):
            return "garbled font map" if extraction_mode != "layout" else "###"

    class FakeReader:
        def __init__(self, _stream):
            self.pages = [FakePage()]

    monkeypatch.setattr(legal_research, "_ocr_pdf_pages", lambda _bytes: (
        "قانون الخدمة المدنية رقم 81 لسنة 2016 والوظائف المدنية حق للمواطنين "
        "على أساس الكفاءة والجدارة"
    ))
    monkeypatch.setitem(
        __import__("sys").modules,
        "pypdf",
        __import__("types").SimpleNamespace(PdfReader=FakeReader),
    )
    extracted = legal_research._extract_pdf_text(b"%PDF-test", "https://www.gov.eg/law.pdf")

    assert "قانون الخدمة المدنية" in extracted
    assert "الكفاءة والجدارة" in extracted


def test_pdf_native_extraction_skips_ocr_when_arabic_text_is_usable(monkeypatch):
    import legal_research

    expected = (
        "قانون الخدمة المدنية رقم 81 لسنة 2016 والوظائف المدنية حق للمواطنين "
        "على أساس الكفاءة والجدارة، وتحدد اللائحة التنفيذية شروط التعيين."
    )

    class FakePage:
        def extract_text(self, extraction_mode=None):
            return expected

    class FakeReader:
        def __init__(self, _stream):
            self.pages = [FakePage()]

    ocr_calls = []
    monkeypatch.setattr(legal_research, "_ocr_pdf_pages", lambda _bytes: ocr_calls.append(True) or "")
    monkeypatch.setitem(
        __import__("sys").modules,
        "pypdf",
        __import__("types").SimpleNamespace(PdfReader=FakeReader),
    )
    extracted = legal_research._extract_pdf_text(b"%PDF-test", "https://www.gov.eg/law.pdf")

    assert "قانون الخدمة المدنية" in extracted
    assert ocr_calls == []
