from blogger_theme_worker import apply_theme_patch, MARKER, PHONE, WHATSAPP


def _minimal_theme():
    return """<?xml version='1.0' encoding='UTF-8'?>
<root xmlns:b='http://www.google.com/2005/gml/b'>
  <b:skin><![CDATA[body { color: black; }]]></b:skin>
  <nav><b:section id='page_list_top'></b:section></nav>
  <main id='main'><b:if cond='data:view.isMultipleItems'>posts</b:if></main>
  <b:includable id='postBody'><data:post.body/></b:includable>
  <b:template-script async='true' name='indie' version='1.0.0'/>
</root>"""


def test_theme_patch_adds_confirmed_contact_links_and_ga4_events():
    updated = apply_theme_patch(_minimal_theme())
    assert MARKER in updated
    assert PHONE in updated
    assert WHATSAPP in updated
    assert "tel:" in updated
    assert "wa.me/" in updated
    assert "contact_click" in updated
    assert "consultation_click" in updated
    assert "target='_blank'" in updated


def test_theme_patch_is_idempotent():
    updated = apply_theme_patch(_minimal_theme())
    assert apply_theme_patch(updated) == updated


def test_theme_patch_fails_closed_when_expected_template_anchor_is_missing():
    import pytest
    with pytest.raises(Exception):
        apply_theme_patch("<root><body>unknown theme</body></root>")
