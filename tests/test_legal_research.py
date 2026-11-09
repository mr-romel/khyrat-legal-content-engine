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
        "SOURCE 1\\n"
        "VERIFIED SOURCE TEXT (retrieved): القانون رقم ١٧٥ لسنة ٢٠١٨ في شأن مكافحة جرائم تقنية المعلومات"
    )
    assert validate_legal_citations(post, packet) == []
