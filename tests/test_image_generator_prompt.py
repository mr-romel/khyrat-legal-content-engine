from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import image_generator
import pytest
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
    monkeypatch.setenv("KHYRAT_IMAGE_PROVIDER_STATE_PATH", str(tmp_path / "provider-state.json"))
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
    assert "generic lawyer portrait" in prompt
    assert "setting appropriate to the described scene" in prompt
    assert "exact subject and action" in prompt
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
    monkeypatch.setenv("KHYRAT_IMAGE_PROVIDER_STATE_PATH", str(tmp_path / "provider-state.json"))
    captured = {}

    def fake_post(url, *, headers, files, timeout):
        captured.update({key: value[1] for key, value in files.items()})
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


def test_flux2_klein_provider_uses_fixed_step_multipart_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("KHYRAT_IMAGE_PROVIDER_STATE_PATH", str(tmp_path / "provider-state.json"))
    captured = {}

    def fake_post(url, *, headers, files, timeout):
        captured["url"] = url
        captured.update({key: value[1] for key, value in files.items()})
        return FakeResponse()

    monkeypatch.setattr(image_generator.requests, "post", fake_post)
    monkeypatch.setattr(image_generator, "_extract_image_bytes", lambda response: _valid_image_bytes())
    monkeypatch.setattr(image_generator, "brand_published_image", lambda path: path)

    output = tmp_path / "klein.jpg"
    image_generator.create_legal_image(
        topic="المرفق العام الاقتصادي",
        image_brief="A modern municipal water treatment plant with tanks and pipes.",
        visual_description="A modern municipal water treatment plant with tanks and pipes.",
        post_context="The public utility provides water services.",
        output_path=str(output),
        cloudflare_account_id="test-account",
        cloudflare_api_token="test-token",
        aspect_ratio="9:16",
        provider="cloudflare_klein",
    )

    assert captured["url"].endswith("/@cf/black-forest-labs/flux-2-klein-9b")
    assert captured["width"] == "576" and captured["height"] == "1024"
    assert "steps" not in captured
    import json
    provenance = json.loads((tmp_path / "klein.jpg.provenance.json").read_text(encoding="utf-8"))
    assert provenance["provider"] == "DIRECT_CLOUDFLARE_KLEIN"
    assert provenance["model"] == "@cf/black-forest-labs/flux-2-klein-9b"


def test_wikimedia_scene_fallback_preserves_license_and_attribution(monkeypatch, tmp_path):
    calls = []

    class SearchResponse(FakeResponse):
        def json(self):
            return {
                "query": {
                    "pages": {
                        "123": {
                            "title": "File:Water treatment plant.jpg",
                            "imageinfo": [{
                                "thumburl": "https://upload.wikimedia.org/example-thumb.jpg",
                                "url": "https://upload.wikimedia.org/example-full.jpg",
                                "mime": "image/jpeg",
                                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Water_treatment_plant.jpg",
                                "extmetadata": {
                                    "LicenseShortName": {"value": "CC BY 4.0"},
                                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by/4.0/"},
                                    "Artist": {"value": "<a href='https://example.com'>Example Photographer</a>"},
                                },
                            }],
                        }
                    }
                }
            }

    class ImageResponse(FakeResponse):
        content = _valid_image_bytes()
        headers = {"content-type": "image/jpeg"}

    def fake_get(url, **kwargs):
        calls.append(url)
        return SearchResponse() if "commons.wikimedia.org/w/api.php" in url else ImageResponse()

    monkeypatch.setattr(image_generator.requests, "get", fake_get)
    monkeypatch.setattr(image_generator, "brand_published_image", lambda path: path)

    output = tmp_path / "commons.jpg"
    image_generator.create_legal_image(
        topic="المرفق العام الاقتصادي",
        image_brief="A modern municipal water treatment plant with tanks and pipes.",
        visual_description="A modern municipal water treatment plant with tanks and pipes.",
        post_context="The public utility provides water services.",
        output_path=str(output),
        aspect_ratio="9:16",
        provider="wikimedia",
    )

    import json
    provenance = json.loads((tmp_path / "commons.jpg.provenance.json").read_text(encoding="utf-8"))
    assert provenance["provider"] == "WIKIMEDIA_COMMONS_SCENE"
    assert provenance["source_metadata"]["license"] == "CC BY 4.0"
    assert provenance["source_metadata"]["artist"] == "Example Photographer"
    assert provenance["source_metadata"]["attribution_required"] == "true"
    assert len(calls) == 2


def test_openverse_scene_fallback_preserves_cc_by_attribution(monkeypatch, tmp_path):
    import json
    import free_media

    def fake_fetch_openverse_images(terms, output_dir, per_term=5):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        asset = output_dir / "openverse-water-treatment.png"
        asset.write_bytes(_valid_image_bytes())
        sources = [{
            "file": str(asset),
            "title": "Water treatment plant",
            "description": "Municipal water treatment facility with filtration tanks.",
            "tags": ["water", "treatment", "plant", "municipal"],
            "creator": "Example Openverse Photographer",
            "license": "by",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "source": "flickr",
            "source_url": "https://example.org/source-page",
            "media_url": "https://example.org/media.jpg",
        }]
        (output_dir / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
        return [asset]

    monkeypatch.setattr(free_media, "fetch_openverse_images", fake_fetch_openverse_images)
    monkeypatch.setattr(image_generator, "brand_published_image", lambda path: path)

    output = tmp_path / "openverse.jpg"
    image_generator.create_legal_image(
        topic="المرفق العام الاقتصادي",
        image_brief="A modern municipal water treatment plant with tanks and pipes.",
        visual_description="A modern municipal water treatment plant with tanks and pipes.",
        post_context="The public utility provides water services.",
        output_path=str(output),
        aspect_ratio="9:16",
        provider="openverse",
    )

    provenance = json.loads((tmp_path / "openverse.jpg.provenance.json").read_text(encoding="utf-8"))
    assert provenance["provider"] == "OPENVERSE_SCENE_STOCK"
    assert provenance["model"] == "openverse-scene-search"
    assert provenance["source_metadata"]["source"] == "Openverse"
    assert provenance["source_metadata"]["license"] == "CC BY"
    assert provenance["source_metadata"]["artist"] == "Example Openverse Photographer"
    assert provenance["source_metadata"]["attribution_required"] == "true"


def test_image_regeneration_brief_preserves_people_actions_and_required_props():
    original = (
        "A clerk and two business partners reviewing a criminal case checklist "
        "at a modern legal office desk with a case file, pen and signed statement."
    )
    regenerated = image_generator.build_image_regeneration_brief(
        original,
        "Make the checklist and case file more prominent; remove unrelated objects.",
    )
    assert original in regenerated
    assert "A clerk and two business partners" in regenerated
    assert "every required subject, person, action" in regenerated.lower()
    assert "Avoid people and hands" not in regenerated
    assert "do not replace the scene with a still life" in regenerated.lower()


def test_image_regeneration_brief_requires_the_original_scene():
    import pytest
    with pytest.raises(ValueError, match="original visual brief"):
        image_generator.build_image_regeneration_brief("", "Fix the scene.")



def test_each_post_gets_a_distinct_row_specific_composition_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv("KHYRAT_IMAGE_PROVIDER_STATE_PATH", str(tmp_path / "provider-state.json"))
    prompts = []

    def fake_post(url, *, headers, files, timeout):
        prompts.append(files["prompt"][1])
        return FakeResponse()

    monkeypatch.setattr(image_generator.requests, "post", fake_post)
    monkeypatch.setattr(image_generator, "_extract_image_bytes", lambda response: _valid_image_bytes())
    monkeypatch.setattr(image_generator, "brand_published_image", lambda path: path)

    common = {
        "topic": "القرارات الإدارية",
        "image_brief": "A company manager reviewing an official administrative decision at a desk.",
        "visual_description": "A company manager reviewing an official administrative decision at a desk.",
        "post_context": "A legal post explaining how to challenge an administrative decision.",
        "cloudflare_account_id": "test-account",
        "cloudflare_api_token": "test-token",
    }
    image_generator.create_legal_image(output_path=str(tmp_path / "row-101.jpg"), **common)
    image_generator.create_legal_image(output_path=str(tmp_path / "row-102.jpg"), **common)

    assert len(prompts) == 2
    assert prompts[0] != prompts[1]
    assert "POST-SPECIFIC VISUAL VARIATION" in prompts[0]
    assert "POST-SPECIFIC VISUAL VARIATION" in prompts[1]
    assert "VISUAL ID:" in prompts[0]
    assert "VISUAL ID:" in prompts[1]



def test_local_scene_provider_is_rejected_to_prevent_placeholder_art(monkeypatch, tmp_path):
    import pytest

    output = tmp_path / "identity-impersonation.jpg"
    with pytest.raises(image_generator.ImageGenerationError, match="Unsupported image provider preference"):
        image_generator.create_legal_image(
            topic="انتحال الشخصية",
            image_brief="Identity verification scene with no text.",
            visual_description="Identity verification scene with no text.",
            post_context="انتحال الشخصية وإجراءات التحقق من الهوية",
            output_path=str(output),
            provider="local_scene",
        )
    assert not output.exists()



def test_duplicate_post_image_guard_rejects_same_visual(tmp_path):
    import pytest

    reference_dir = tmp_path / "generated"
    reference_dir.mkdir()
    first = reference_dir / "old-post.jpg"
    current = reference_dir / "new-post.jpg"

    image = Image.effect_noise((640, 800), 80).convert("RGB")
    image.save(first, format="JPEG", quality=94)
    image.save(current, format="JPEG", quality=94)

    with pytest.raises(image_generator.ImageGenerationError, match="DUPLICATE_POST_IMAGE_BLOCKED"):
        image_generator.assert_image_not_duplicate(str(current), reference_dir=str(reference_dir))


def test_duplicate_post_image_guard_allows_different_visual(tmp_path):
    reference_dir = tmp_path / "generated"
    reference_dir.mkdir()
    first = reference_dir / "old-post.jpg"
    current = reference_dir / "new-post.jpg"

    Image.effect_noise((640, 800), 20).convert("RGB").save(first, format="JPEG", quality=94)
    Image.effect_noise((640, 800), 110).convert("RGB").save(current, format="JPEG", quality=94)

    image_generator.assert_image_not_duplicate(str(current), reference_dir=str(reference_dir))


def test_duplicate_guard_returns_hash_without_reference_directory(tmp_path):
    image_path = tmp_path / "new.jpg"
    Image.effect_noise((640, 800), 75).convert("RGB").save(image_path, format="JPEG", quality=94)
    result = image_generator.assert_image_not_duplicate(
        str(image_path), reference_dir=str(tmp_path / "not-created")
    )
    import hashlib
    assert result == hashlib.sha256(image_path.read_bytes()).hexdigest()


def test_duplicate_guard_rejects_hash_from_persistent_registry(tmp_path):
    image_path = tmp_path / "new.jpg"
    Image.effect_noise((640, 800), 75).convert("RGB").save(image_path, format="JPEG", quality=94)
    import hashlib
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    with pytest.raises(image_generator.ImageGenerationError, match="DUPLICATE_POST_IMAGE_BLOCKED"):
        image_generator.assert_image_not_duplicate(
            str(image_path), reference_dir=str(tmp_path / "empty"), known_hashes={digest}
        )



def test_pixabay_query_uses_scene_nouns_not_camera_direction():
    query, fallback = image_generator._pixabay_scene_queries(
        "امتناع الإدارة عن اتخاذ القرار",
        (
            "A mid-shot of a neutral-looking adult seated at a modern office desk, "
            "hands resting on an open folder, request form, law-book, clipboard, checklist, "
            "wall clock and calendar."
        ),
    )
    assert "government" in query
    assert "office" in query
    assert "paperwork" in query
    assert "documents" in query
    assert "mid" not in query and "shot" not in query and "neutral" not in query
    assert fallback == "office paperwork documents folder"


def test_pixabay_selects_only_metadata_matched_image_and_records_provenance(monkeypatch, tmp_path):
    import json

    monkeypatch.setenv("PIXABAY_API_KEY", "test-pixabay-key")
    monkeypatch.setenv("KHYRAT_IMAGE_PROVIDER_STATE_PATH", str(tmp_path / "provider-state.json"))
    calls = []

    class SearchResponse(FakeResponse):
        def json(self):
            return {
                "hits": [
                    {
                        "id": 11,
                        "tags": "beach, sea, summer, travel",
                        "largeImageURL": "https://images.example/irrelevant.jpg",
                        "pageURL": "https://pixabay.com/photos/irrelevant-11/",
                        "user": "irrelevant-user",
                    },
                    {
                        "id": 22,
                        "tags": "office, paperwork, documents, folder, desk",
                        "largeImageURL": "https://images.example/office-documents.jpg",
                        "pageURL": "https://pixabay.com/photos/office-documents-22/",
                        "user": "editorial-user",
                    },
                ]
            }

    class ImageResponse(FakeResponse):
        content = _valid_image_bytes()
        headers = {"content-type": "image/jpeg"}

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return SearchResponse() if url == "https://pixabay.com/api/" else ImageResponse()

    monkeypatch.setattr(image_generator.requests, "get", fake_get)
    monkeypatch.setattr(image_generator, "brand_published_image", lambda path: path)

    output = tmp_path / "pixabay-scene.jpg"
    image_generator.create_legal_image(
        topic="امتناع الإدارة عن اتخاذ القرار",
        image_brief="An administrative office desk with paperwork and a file.",
        visual_description="An adult seated at an office desk with an open folder, paperwork and documents.",
        post_context="The post explains an administration's refusal to take a legally required decision.",
        output_path=str(output),
        aspect_ratio="9:16",
        provider="pixabay",
    )

    provenance = json.loads((tmp_path / "pixabay-scene.jpg.provenance.json").read_text(encoding="utf-8"))
    assert provenance["provider"] == "PIXABAY_SCENE_STOCK"
    assert provenance["source_metadata"]["image_id"] == "22"
    assert provenance["source_metadata"]["source_page"] == "https://pixabay.com/photos/office-documents-22/"
    assert provenance["source_metadata"]["search_query"] == "government office paperwork documents desk folder"
    assert len(calls) == 2
    assert calls[0][1]["params"]["q"] == provenance["source_metadata"]["search_query"]
    assert calls[1][0] == "https://images.example/office-documents.jpg"
