from legal_research import _case, _date, _effective, _quote

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
