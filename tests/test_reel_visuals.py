from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reel_pipeline import post_visual_terms, topic_visual_terms


def test_secret_disclosure_visuals_are_specific_to_digital_threat_evidence():
    terms = post_visual_terms(
        "التهديد بإفشاء الأسرار عبر رسائل خاصة، مع ضرورة حفظ الرسائل وتوقيتاتها وإثبات نسبتها.",
        "التهديد بإفشاء الأسرار",
    )
    joined = " ".join(terms).lower()
    assert len(terms) >= 8
    assert "threatening" in joined
    assert "smartphone" in joined
    assert "timestamp" in joined or "date and time" in joined
    assert "confidential" in joined
    assert "courtroom" not in joined
    assert "gavel" not in joined


def test_secret_disclosure_topic_visual_fallback_is_not_generic_legal_stock():
    terms = topic_visual_terms("التهديد بإفشاء الأسرار")
    assert len(terms) >= 8
    assert any("threatening" in item for item in terms)
    assert any("confidential" in item for item in terms)
    assert any("smartphone" in item for item in terms)



def test_secret_threat_visual_pack_never_mixes_unauthorized_recording():
    terms = post_visual_terms(
        "التهديد بإفشاء الأسرار عبر رسائل خاصة. كما ورد في الملف موضوع تصوير دون إذن في مكان عام.",
        "التهديد بإفشاء الأسرار",
    )
    joined = " ".join(terms).lower()
    assert len(terms) == 8
    assert "threatening private message" in joined
    assert "timestamp" in joined
    assert "recording" not in joined
    assert "camera" not in joined
    assert "public place" not in joined


def test_unauthorized_recording_visual_pack_does_not_use_secret_threat_scenes():
    terms = post_visual_terms(
        "التصوير دون إذن في مكان عام واستخدام الهاتف لتسجيل الأشخاص.",
        "التصوير دون إذن",
    )
    joined = " ".join(terms).lower()
    assert len(terms) == 8
    assert "smartphone camera" in joined or "phone camera" in joined
    assert "public-place" in joined or "public place" in joined
    assert "threatening private message" not in joined
    assert "confidential files" not in joined


def test_model_or_mixed_post_terms_cannot_override_authoritative_topic_family():
    terms = post_visual_terms(
        "موضوع مختلط عن عقد عمل وتصوير دون إذن وتهديد بإفشاء الأسرار.",
        "حقوق العامل عند الفصل",
    )
    joined = " ".join(terms).lower()
    assert len(terms) == 8
    assert "employment contract" in joined
    assert "payroll" in joined or "attendance" in joined
    assert "threatening private message" not in joined
    assert "smartphone camera" not in joined


def test_generic_sheet_topic_infers_visual_family_from_approved_post():
    terms = post_visual_terms(
        "نزاع بين شريكين في شركة حول توزيع الحصص وصلاحيات الإدارة، مع مراجعة عقد التأسيس ومحاضر الشركة.",
        "محتوى قانوني",
    )
    joined = " ".join(terms).lower()
    assert len(terms) == 8
    assert "business partners" in joined
    assert "shareholding agreement" in joined or "corporate registry" in joined
    assert "courtroom" not in joined


def test_economic_public_utility_uses_its_own_visual_family():
    from reel_pipeline import _visual_topic_family

    topic = "المرفق العام الاقتصادي"
    post = "المرفق العام الاقتصادي ينظم تقديم الخدمات الأساسية للجمهور، وتختلف طبيعته عن نشاط الشركة التجاري."
    assert _visual_topic_family(topic) == "public_utility"
    assert _visual_topic_family(post) == "public_utility"
    terms = post_visual_terms(post, topic)
    joined = " ".join(terms).lower()
    assert len(terms) == 8
    assert "public utility" in joined or "public-service" in joined
    assert "shareholding agreement" not in joined


def test_image_prompt_preserves_primary_scene_before_long_source_context():
    from brand_identity import build_editorial_image_prompt

    scene = "UNIQUE_SCENE_ANCHOR municipal water treatment plant with large filtration tanks and industrial pipes"
    prompt = build_editorial_image_prompt(
        topic="المرفق العام الاقتصادي",
        post_context="LONG_SOURCE_CONTEXT " * 500,
        visual_description=scene,
    )
    assert "UNIQUE_SCENE_ANCHOR" in prompt
    assert prompt.index("UNIQUE_SCENE_ANCHOR") < prompt.index("SHORT SOURCE CONTEXT")
    assert len(prompt) < 2048



def test_reel_generation_is_limited_to_five_distinct_images():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert "reel_scene_count = 5" in source
    assert "reel_scene_count = 6" not in source
    assert '1: "pollinations"' in source


def test_reel_workflows_pass_repository_pollinations_secret():
    root = Path(__file__).resolve().parents[1]
    workflows = [
        ".github/workflows/reel-now.yml",
        ".github/workflows/reel-daily-generator.yml",
        ".github/workflows/reel-regenerate-rejected.yml",
    ]
    for relative in workflows:
        content = (root / relative).read_text(encoding="utf-8")
        assert "POLLINATIONS_API_KEY: ${{ secrets.POLLINATIONS_API_KEY }}" in content


def test_explicit_pollinations_provider_does_not_fall_through_to_hidden_providers():
    source = (Path(__file__).resolve().parents[1] / "src" / "image_generator.py").read_text(encoding="utf-8")
    branch = source.index('elif provider_preference == "pollinations":')
    next_branch = source.index('elif image_bytes is None and provider_preference != "gemini":', branch)
    explicit_branch = source[branch:next_branch]
    assert "image_bytes = _generate_with_pollinations()" in explicit_branch
    assert "Gemini" not in explicit_branch
