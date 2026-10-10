from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import image_generator


class FakeResponse:
    ok = True
    status_code = 200

    def json(self):
        return {}


def test_legal_image_generation_prompt_is_positive_and_post_specific(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(json)
        return FakeResponse()

    monkeypatch.setattr(image_generator.requests, "post", fake_post)
    monkeypatch.setattr(image_generator, "_extract_image_bytes", lambda response: b"fake-image-bytes")
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

    assert output.read_bytes() == b"fake-image-bytes"
    prompt = captured["prompt"].lower()
    negative = captured["negative_prompt"].lower()
    assert "worker reviewing a modern employment document" in prompt
    assert "contemporary editorial photograph" in prompt
    for trigger in ("egypt", "egyptian", "pharaoh", "pyramid", "hieroglyph", "sarcophagus", "ancient egypt"):
        assert trigger not in prompt
        assert trigger not in negative

    import json
    provenance = json.loads((tmp_path / "legal.jpg.provenance.json").read_text(encoding="utf-8"))
    assert provenance["provider"] == "DIRECT_CLOUDFLARE"
    assert provenance["prompt_sha256"]
    assert provenance["image_sha256"]
    assert provenance["qa_decision"] == "PENDING"
