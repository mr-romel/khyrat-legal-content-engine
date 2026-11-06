from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brand_identity import (
    BRAND_DESCRIPTOR, BRAND_LOCKUP, BRAND_NAME, BRAND_SERVICE_AREA,
    BRAND_SLOGAN, PROFESSIONAL_NAME, PROFESSIONAL_TITLE, BRAND_OVERLAY_TEXT,
    FACEBOOK_BADGE_BLUE, BLOGGER_BADGE_GREEN,
    build_editorial_image_prompt,
)


def test_canonical_brand_identity_is_complete_and_not_companies_only():
    assert BRAND_NAME == "اسأل محمود"
    assert PROFESSIONAL_NAME == "محمود خيرت رجب"
    assert PROFESSIONAL_TITLE == "محامٍ ومستشار قانوني في مصر"
    assert "أفراد" in BRAND_DESCRIPTOR and "الشركات" in BRAND_DESCRIPTOR
    assert "القاهرة والجيزة" in BRAND_SERVICE_AREA
    assert "جميع محافظات مصر" in BRAND_SERVICE_AREA
    assert "محمود خيرت رجب" in BRAND_LOCKUP
    assert "اسأل محمود" in BRAND_SLOGAN


def test_visual_prompt_is_grounded_in_topic_and_post_context():
    prompt = build_editorial_image_prompt(
        topic="نزاع بشأن مستندات العمل",
        post_context="شرح أهمية الاحتفاظ برسائل التكليف وإثبات ساعات العمل",
        visual_description="A worker organizing dated work records and message screenshots on a desk.",
    )
    assert "نزاع بشأن مستندات العمل" in prompt
    assert "إثبات ساعات العمل" in prompt
    assert "dated work records" in prompt
    assert "generic lawyer portrait" in prompt
    assert "invented legal documents" in prompt


def test_visual_prompt_requires_a_concrete_brief():
    try:
        build_editorial_image_prompt(topic="موضوع قانوني", post_context="", visual_description="")
    except ValueError as exc:
        assert "visual description" in str(exc)
    else:
        raise AssertionError("A generic topic must not be enough to generate an image.")



def test_image_brand_lockup_and_platform_colors_are_fixed():
    assert BRAND_OVERLAY_TEXT == "اسأل محمود خيرت"
    assert FACEBOOK_BADGE_BLUE == (24, 119, 242)
    assert BLOGGER_BADGE_GREEN == (76, 175, 80)
