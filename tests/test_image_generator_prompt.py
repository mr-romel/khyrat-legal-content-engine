from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import image_generator
from PIL import Image
from io import BytesIO


def _valid_image_bytes():
    buffer = BytesIO()
    Image.new("RGB", (1024, 1024), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class FakeResponse:
    ok = True
    status_code = 200

    def json(self):
        return {}


def test_legal_image_generation_prompt_is_positive_and_post_specific(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, *, headers, files, timeout):
        captured.update({key: value[1] for key, value in files.items()})
        return FakeResponse()

    monkeypatch.setattr(image_generator.requests, "post", fake_post)
    monkeypatch.setattr(image_generator, "_extract_image_bytes", lambda response: _valid_image_bytes())
    monkeypatch.setattr(image_generator, "brand_published_image", lambda path: path)

    output = tmp_path / "legal.jpg"
    image_generator.create_legal_image(
        topic="نزاع بشأن مستندات عمل",
        image_brief="A worker reviewing a modern employment document beside a phone at a desk.",
        visual_description="A worker reviewing a modern employment document beside a phone at a desk.",
        post_context="A post about preserving employment records and messages.",
        output_path=str(output),
        cloudflare_account_id="test-account",
        cloudflare_api_token="test-token",
    )

    with Image.open(output) as generated:
        assert generated.size == (1024, 1280)
    assert "negative_prompt" not in captured
    assert captured["width"] == "1024" and captured["height"] == "1280"
    assert captured["steps"] == "25" and captured["guidance"] == "4.5"
    prompt = captured["prompt"]
    assert "A worker reviewing a modern employment document beside a phone at a desk." in prompt
    assert "نزاع بشأن مستندات عمل" in prompt
    assert "preserving employment records and messages" in prompt
    assert "do not substitute a generic lawyer portrait" in prompt
    assert "present-day Egyptian setting" in prompt
    assert "No ancient Egyptian, Pharaonic, archaeological, fantasy or historical imagery" in prompt
    assert "invented legal documents" in prompt
    assert "COMPOSITION FORMAT: portrait 4:5" in prompt

    import json
    provenance = json.loads((tmp_path / "legal.jpg.provenance.json").read_text(encoding="utf-8"))
    assert provenance["provider"] == "DIRECT_CLOUDFLARE"
    assert provenance["model"] == "@cf/black-forest-labs/flux-2-dev"
    assert provenance["prompt_sha256"]
    assert provenance["image_sha256"]
    assert provenance["qa_decision"] == "PENDING"



def test_reel_image_generation_uses_native_vertical_dimensions(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(json)
        return FakeResponse()

    monkeypatch.setattr(image_generator.requests, "post", fake_post)
    monkeypatch.setattr(image_generator, "_extract_image_bytes", lambda response: _valid_image_bytes())
    monkeypatch.setattr(image_generator, "brand_published_image", lambda path: path)

    output = tmp_path / "reel-scene.jpg"
    image_generator.create_legal_image(
        topic="إثبات ساعات العمل",
        image_brief="A close-up of dated work records beside a phone.",
        visual_description="A close-up of dated work records beside a phone.",
        post_context="The post explains how to preserve work records.",
        output_path=str(output),
        cloudflare_account_id="test-account",
        cloudflare_api_token="test-token",
        aspect_ratio="9:16",
    )
    with Image.open(output) as generated:
        assert generated.size == (576, 1024)
    assert "COMPOSITION FORMAT: portrait 9:16" in captured["prompt"]
    import json
    provenance = json.loads((tmp_path / "reel-scene.jpg.provenance.json").read_text(encoding="utf-8"))
    assert provenance["aspect_ratio"] == "9:16"
