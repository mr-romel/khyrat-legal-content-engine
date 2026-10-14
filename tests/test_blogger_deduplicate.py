import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from deduplicate_blogger_articles import fingerprint, normalize

def test_arabic_diacritics_and_punctuation_do_not_change_fingerprint():
    assert normalize("مُحَامِي — قانوني") == normalize("محامي قانوني")

def test_short_content_is_not_eligible_for_deletion():
    assert fingerprint({"content":"قصير"}) == ""

def test_same_body_wrapped_in_different_html_has_same_fingerprint():
    a={"content":"<h1>عنوان</h1><p>" + ("شرح قانوني واضح " * 50) + "</p>"}
    b={"content":"<article><strong>عنوان</strong><div>" + ("شرح قانوني واضح " * 50) + "</div></article>"}
    assert fingerprint(a)==fingerprint(b)

def test_different_bodies_have_different_fingerprints():
    a={"content":"<p>" + ("حقوق العامل في الفصل " * 40) + "</p>"}
    b={"content":"<p>" + ("تأسيس الشركات وإجراءات التسجيل " * 40) + "</p>"}
    assert fingerprint(a)!=fingerprint(b)
