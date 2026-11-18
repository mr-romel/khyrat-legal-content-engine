from blogger_theme_worker import apply_theme_patch, MARKER, PHONE, WHATSAPP, SITE_META_DESCRIPTION


def _minimal_theme():
    return """<?xml version='1.0' encoding='UTF-8'?>
<root xmlns:b='http://www.google.com/2005/gml/b' xmlns:data='http://www.google.com/2005/gml/data'>
  <b:skin><![CDATA[body { color: black; }]]></b:skin>
  <b:section id='ads' ads='true'><b:widget id='AdSense1' visible='false'></b:widget><b:widget id='AdSense2' visible='false'></b:widget></b:section>
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
    assert "event_callback" in updated
    assert "event_timeout" in updated
    assert SITE_META_DESCRIPTION in updated
    assert updated.count("name='description'") == 3
    assert "window.setTimeout(continueToContact, 1100)" in updated
    assert "wa.target = '_blank'" in updated
    assert "AdSense1" not in updated
    assert "AdSense2" not in updated


def test_theme_patch_is_idempotent():
    updated = apply_theme_patch(_minimal_theme())
    assert apply_theme_patch(updated) == updated


def test_theme_patch_migrates_v3_tracking_and_meta_description_without_duplicating_layout():
    from blogger_theme_worker import PREVIOUS_MARKER
    legacy = apply_theme_patch(_minimal_theme()).replace(MARKER, PREVIOUS_MARKER)
    migrated = apply_theme_patch(legacy)
    assert MARKER in migrated
    assert PREVIOUS_MARKER not in migrated
    assert SITE_META_DESCRIPTION in migrated
    assert migrated.count("name='description'") == 2
    assert migrated.count("Khyrat Legal: GA4 lead-event tracking") == 1
    assert "event_callback" in migrated


def test_theme_patch_fails_closed_when_expected_template_anchor_is_missing():
    import pytest
    with pytest.raises(Exception):
        apply_theme_patch("<root><body>unknown theme</body></root>")
