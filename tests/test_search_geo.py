from search_geo import build_metadata


def test_answer_extract_removes_html_and_decodes_entities():
    item = build_metadata(
        post_id="1",
        topic="حقوق العامل في مصر",
        post="<p>يستحق العامل حقوقه وفقًا للقواعد المنظمة لعلاقة العمل.</p>",
        platform="BLOGGER",
    )
    assert "<p>" not in item["Answer Extract"]
    assert "يستحق العامل" in item["Answer Extract"]


def test_missing_legal_sources_are_not_described_as_verified():
    item = build_metadata(
        post_id="2",
        topic="إجراء قانوني عام",
        post="تختلف الإجراءات بحسب الوقائع والمستندات.",
        platform="BLOGGER",
    )
    assert "لم تُرفق مصادر قانونية محددة" in item["Supporting Evidence"]
    assert "تستلزم مراجعة قانونية بشرية" in item["Author/Provenance"]


def test_sheet_id_accepts_verified_sheet_url_when_id_secret_is_absent(monkeypatch):
    from config import _sheet_id

    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    monkeypatch.setenv("GOOGLE_SHEET_URL", "https://docs.google.com/spreadsheets/d/abc_123-XYZ/edit#gid=0")
    assert _sheet_id() == "abc_123-XYZ"


def test_sheet_id_prefers_explicit_id_over_url(monkeypatch):
    from config import _sheet_id

    monkeypatch.setenv("GOOGLE_SHEET_ID", "explicit-sheet-id")
    monkeypatch.setenv("GOOGLE_SHEET_URL", "https://docs.google.com/spreadsheets/d/url-sheet-id/edit")
    assert _sheet_id() == "explicit-sheet-id"
