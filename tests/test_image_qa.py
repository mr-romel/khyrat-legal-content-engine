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


def test_qa_prompt_preserves_reference_as_identity_source():
    prompt = _build_prompt(
        "نزاع حول توقيع عقد",
        "A realistic office scene showing the disputed contract being reviewed.",
        {"width": 1024, "height": 1280, "aspect_ratio": 0.8, "aspect_ratio_ok": True},
        3,
        "REFERENCE_SUBJECT",
    )
    assert "identity source" in prompt
    assert "new pose/scene" in prompt
    assert "bottom-right overlay" in prompt
    assert "legal situation" in prompt
