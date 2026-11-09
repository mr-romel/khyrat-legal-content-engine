from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image
from image_qa import _hard_checks, _build_prompt


def test_final_image_hard_check_accepts_4x5(tmp_path):
    path = tmp_path / "image.jpg"
    Image.new("RGB", (1024, 1280), "white").save(path)
    result = _hard_checks(path)
    assert result["aspect_ratio_ok"] is True
    assert result["width"] == 1024
    assert result["height"] == 1280


def test_final_image_hard_check_rejects_non_4x5(tmp_path):
    path = tmp_path / "image.jpg"
    Image.new("RGB", (1024, 1024), "white").save(path)
    result = _hard_checks(path)
    assert result["aspect_ratio_ok"] is False


def test_qa_prompt_is_context_only_and_never_requires_reference_identity():
    prompt = _build_prompt(
        "نزاع حول توقيع عقد",
        "A realistic office scene showing the disputed contract being reviewed.",
        {"width": 1024, "height": 1280, "aspect_ratio": 0.8, "aspect_ratio_ok": True},
        0,
        "CONTEXT_ONLY",
    )
    assert "identity source" not in prompt
    assert "generated scene must be new" in prompt
    assert "bottom overlay" in prompt
    assert "BRAND OVERLAY RULE" in prompt
    assert "اسال محمود خيرت - محام ومستشار قانوني" in prompt
    assert "No platform-specific icon is used" in prompt
    assert "legal situation" in prompt
    assert "Do not impose an unrequested country" in prompt
    assert "Any visual style or setting is acceptable" in prompt
    assert "materially relevant to the legal issue" in prompt
    assert "Do not invent negative constraints" in prompt
    assert "The absence of a person, lawyer, courtroom" in prompt



def test_qa_prompt_explicitly_requires_regeneration_for_anatomy_defects():
    prompt = _build_prompt(
        "نزاع حول توقيع عقد",
        "A present-day contract review scene.",
        {"width": 1024, "height": 1280, "aspect_ratio": 0.8, "aspect_ratio_ok": True},
        0,
        "CONTEXT_ONLY",
    )
    assert "visibly fused limb" in prompt
    assert "impossible" in prompt
    assert "A clearly visible, material anatomy or geometry defect is a valid rejection reason" in prompt



def test_qa_prompt_treats_visible_distortion_as_mandatory_regeneration():
    prompt = _build_prompt(
        "نزاع حول توقيع عقد",
        "A contemporary contract review scene.",
        {"width": 1024, "height": 1280, "aspect_ratio": 0.8, "aspect_ratio_ok": True},
        0,
        "CONTEXT_ONLY",
    )
    assert "visibly distorted" in prompt
    assert "Do not reject solely for advisory scores" in prompt
    assert "ambiguous reflections" in prompt


def test_image_qa_without_key_does_not_block_publication(tmp_path):
    from image_qa import qa_image
    path = tmp_path / "image.jpg"
    Image.new("RGB", (1024, 1024), "white").save(path)
    result = qa_image(api_key="", image_path=str(path), topic="test", image_brief="test")
    assert result["decision"] == "QA_UNAVAILABLE"
    assert "cannot be cleared for publication" in result["issues"][0]


def test_image_qa_api_error_fails_closed(monkeypatch, tmp_path):
    from image_qa import qa_image
    path = tmp_path / "image.jpg"
    Image.new("RGB", (576, 1024), "white").save(path)

    class BrokenModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("temporary QA outage")

    class BrokenClient:
        models = BrokenModels()

    monkeypatch.setattr("image_qa.genai.Client", lambda **kwargs: BrokenClient())
    result = qa_image(api_key="test-key", image_path=str(path), topic="test", image_brief="test")
    assert result["decision"] == "QA_UNAVAILABLE"
    assert "cannot be cleared for publication" in result["issues"][0]
