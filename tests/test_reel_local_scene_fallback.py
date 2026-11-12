from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reel_uses_local_scene_renderer_after_metered_providers_and_never_stock_search():
    source = (ROOT / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert '1: "pollinations"' in source
    assert '2: "cloudflare"' in source
    assert '3: "local_scene"' in source
    assert '4: "wikimedia"' not in source
    assert '5: "pixabay"' not in source
    assert "_generate_scene_with_provider_fallbacks" in source
    assert "REEL_SCENE_VISUAL_QA_REJECTED" in source


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


def test_local_scene_provider_creates_valid_public_utility_image_without_api_key(tmp_path):
    import sys
    import json
    sys.path.insert(0, str(ROOT / "src"))
    from image_generator import create_legal_image
    from image_qa import qa_image
    from PIL import Image

    output = tmp_path / "public-utility.jpg"
    brief = "A modern municipal water treatment plant with large filtration tanks and industrial pipes."
    create_legal_image(
        topic="المرفق العام الاقتصادي",
        image_brief=brief,
        visual_description=brief,
        post_context="The public utility provides water services.",
        output_path=str(output),
        aspect_ratio="9:16",
        provider="local_scene",
    )
    with Image.open(output) as image:
        assert image.size == (576, 1024)
    provenance = json.loads(output.with_suffix(".jpg.provenance.json").read_text(encoding="utf-8"))
    assert provenance["provider"] == "LOCAL_SCENE_ILLUSTRATION"
    assert provenance["source_metadata"]["external_provider"] == "false"
    result = qa_image(api_key="", image_path=str(output), topic="المرفق العام الاقتصادي", image_brief=brief)
    assert result["decision"] == "PASS"
    assert result["qa_method"] == "local-renderer-provenance-and-integrity"


def test_recovery_queue_never_retries_topic_source_mismatch_as_an_image_failure():
    workflow = (ROOT / ".github" / "workflows" / "reel-regenerate-rejected.yml").read_text(encoding="utf-8")
    assert "retryable_legacy_mapping_failure" not in workflow
    assert 'last_error.startswith("REEL_SOURCE_TOPIC_MISMATCH")' not in workflow
    assert "Topic mismatch is a source-integrity failure, not an image-provider" in workflow
    assert "retryable_failure = retryable_image_failure" in workflow


def test_one_time_recovery_pin_uses_immutable_id_and_bounded_retries():
    workflow = (ROOT / ".github" / "workflows" / "reel-regenerate-rejected.yml").read_text(encoding="utf-8")
    assert 'REEL_RECOVERY_SOURCE_ID: "20261111-1000-R011"' in workflow
    assert 'source_id == os.getenv("REEL_RECOVERY_SOURCE_ID", "").strip()' in workflow
    assert 'status == "FAILED"' in workflow
    assert "retry_count < 3" in workflow
    assert "explicit source-ID recovery" in workflow
    assert '"row_number": number' in workflow


def test_image_provider_timeout_is_bounded_and_configurable(monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from image_generator import _image_provider_timeout_seconds

    monkeypatch.setenv("REEL_IMAGE_PROVIDER_TIMEOUT_SECONDS", "45")
    assert _image_provider_timeout_seconds() == 45
    monkeypatch.setenv("REEL_IMAGE_PROVIDER_TIMEOUT_SECONDS", "999")
    assert _image_provider_timeout_seconds() == 120
    monkeypatch.setenv("REEL_IMAGE_PROVIDER_TIMEOUT_SECONDS", "invalid")
    assert _image_provider_timeout_seconds() == 60


def test_scene_visual_qa_rejection_falls_through_to_next_provider_and_local_scene(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from reel_pipeline import _generate_scene_with_provider_fallbacks

    used = []
    def fake_create(**kwargs):
        provider = kwargs["provider"]
        used.append(provider)
        Path(kwargs["output_path"]).write_bytes((provider.encode("ascii") * 6000)[:12000])

    def fake_qa(**kwargs):
        # Simulate the exact incident: both generated images are unrelated,
        # while the quota-free original local scene passes its provenance gate.
        provider = Path(kwargs["image_path"]).read_bytes().decode("ascii", errors="ignore")
        return {"decision": "PASS" if provider.startswith("local_scene") else "REGENERATE",
                "issues": ["off-topic generated scene"]}

    result = _generate_scene_with_provider_fallbacks(
        topic="المرفق العام الاقتصادي",
        post="خدمات المرافق العامة الاقتصادية",
        image_brief="Municipal water treatment plant with tanks and pipes",
        output_path=tmp_path / "scene.jpg",
        api_key="",
        cloudflare_account_id="",
        cloudflare_api_token="",
        providers={1:"pollinations",2:"cloudflare",3:"local_scene"},
        create_image=fake_create,
        qa_image=fake_qa,
    )
    assert used == ["pollinations", "cloudflare", "local_scene"]
    assert result["provider"] == "local_scene"
    assert result["qa"]["decision"] == "PASS"


def test_tts_fallback_chain_uses_edge_before_google_cloud(monkeypatch, tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    import reel_pipeline

    calls = []
    def fail_gemini(*args, **kwargs):
        calls.append("gemini")
        raise RuntimeError("429 quota")
    def pass_edge(*args, **kwargs):
        calls.append("edge")
        return tmp_path / "voice.mp3"
    def fail_google(*args, **kwargs):
        calls.append("google")
        raise RuntimeError("403 forbidden")
    monkeypatch.setattr(reel_pipeline, "generate_gemini_tts_audio", fail_gemini)
    monkeypatch.setattr(reel_pipeline, "generate_edge_arabic_tts_audio", pass_edge)
    monkeypatch.setattr(reel_pipeline, "generate_google_cloud_arabic_tts_audio", fail_google)
    result = reel_pipeline.generate_reel_narration_with_fallbacks(
        "key", {}, "نص تجريبي", [], tmp_path / "voice.mp3"
    )
    assert result == tmp_path / "voice.mp3"
    assert calls == ["gemini", "edge"]


def test_explicit_source_id_recovery_is_one_shot_even_after_retry_budget_exhaustion():
    workflow = (ROOT / ".github" / "workflows" / "reel-regenerate-rejected.yml").read_text(encoding="utf-8")
    assert 'status in {"FAILED", "REGENERATE_REQUESTED"}' in workflow
    assert '"source-id-recovery-used" not in review.casefold()' in workflow
    assert "source-id-recovery-used" in workflow
    assert 'and retry_count < 3' not in workflow.split("pinned_source_retry = (", 1)[1].split(")", 1)[0]


def test_image_provider_quota_failure_disables_provider_for_remaining_scenes(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from reel_pipeline import _generate_scene_with_provider_fallbacks

    disabled = set()
    calls = []
    def fake_create(**kwargs):
        provider = kwargs["provider"]
        calls.append(provider)
        if provider == "pollinations":
            raise RuntimeError("Pollinations image request failed: HTTP 402 KEY_BUDGET_EXHAUSTED")
        if provider == "cloudflare":
            raise RuntimeError("Cloudflare image provider failed: HTTP 429 daily free allocation")
        Path(kwargs["output_path"]).write_bytes(b"x" * 12000)

    def fake_qa(**kwargs):
        return {"decision": "PASS", "qa_method": "test-local"}

    for index in (1, 2):
        _generate_scene_with_provider_fallbacks(
            topic="المرفق العام الاقتصادي",
            post="خدمات المرافق العامة الاقتصادية",
            image_brief="Municipal water treatment plant with tanks and pipes",
            output_path=tmp_path / f"scene-{index}.jpg",
            api_key="",
            cloudflare_account_id="",
            cloudflare_api_token="",
            providers={1:"pollinations",2:"cloudflare",3:"local_scene"},
            create_image=fake_create,
            qa_image=fake_qa,
            disabled_providers=disabled,
        )
    assert calls == ["pollinations", "cloudflare", "local_scene", "local_scene"]
    assert disabled == {"pollinations", "cloudflare"}


def test_audio_path_fix_rearms_one_new_source_id_recovery_attempt():
    workflow = (ROOT / ".github" / "workflows" / "reel-regenerate-rejected.yml").read_text(encoding="utf-8")
    assert 'REEL_RECOVERY_ATTEMPT_ID: "row21-audio-path-fix-20261112-01"' in workflow
    assert 'pinned_attempt_marker not in review.casefold()' in workflow
    assert 'source-id-recovery-used:{recovery_attempt_id}' in workflow
    assert 'status in {"FAILED", "REGENERATE_REQUESTED"}' in workflow
