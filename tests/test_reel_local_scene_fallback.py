from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reel_uses_local_scene_renderer_after_metered_providers_and_never_stock_search():
    source = (ROOT / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert '1: "pollinations"' in source
    assert '2: "cloudflare"' in source
    assert '3: "local_scene"' in source
    assert '4: "wikimedia"' not in source
    assert '5: "pixabay"' not in source
    assert "deterministic local illustration" in source


def test_local_scene_renderer_has_public_utility_visuals_without_external_api():
    source = (ROOT / "src" / "image_generator.py").read_text(encoding="utf-8")
    assert '"local_scene"' in source
    assert "LOCAL_SCENE_ILLUSTRATION" in source
    assert "Original local renderer" in source
    assert "water treatment" in source
    assert "public transport" in source
    assert "no external image quota consumed" in source


def test_local_scene_qa_requires_matching_provenance_and_image_fingerprint():
    source = (ROOT / "src" / "image_qa.py").read_text(encoding="utf-8")
    assert 'provenance.get("provider") == "LOCAL_SCENE_ILLUSTRATION"' in source
    assert "LOCAL_SCENE_QA_FAILED" in source
    assert 'digest != provenance.get("image_sha256")' in source
    assert "local-renderer-provenance-and-integrity" in source
