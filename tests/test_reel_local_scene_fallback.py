from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reel_scene_providers_prioritize_public_open_license_fallbacks():
    source = (ROOT / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert '1: "pollinations"' in source
    assert '2: "cloudflare"' in source
    assert '3: "gemini"' in source
    assert '4: "openverse"' in source
    assert '5: "wikimedia"' in source
    assert '4: "local_scene"' not in source
    assert "_generate_scene_with_provider_fallbacks" in source
    assert "REEL_SCENE_VISUAL_QA_REJECTED" in source


def test_local_scene_is_not_an_allowed_image_provider_or_automatic_fallback():
    source = (ROOT / "src" / "image_generator.py").read_text(encoding="utf-8")
    main_source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    assert '"pixabay"}' in source
    assert 'provider_preference == "local_scene"' not in source
    assert "LOCAL_SCENE_ILLUSTRATION" not in source
    assert "local/generated placeholder artwork is disabled" in source
    assert "local_scene" not in main_source


def test_article_image_rotation_never_uses_local_artwork():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    assert 'IMAGE_PROVIDER_ROTATION.append("local_scene")' not in source
    assert "_supports_topic_specific_local_scene" not in source


def test_image_recovery_still_requires_topic_specific_qa_and_never_uses_generic_art():
    source = (ROOT / "src" / "image_generator.py").read_text(encoding="utf-8")
    assert "NO_TOPIC_SPECIFIC_IMAGE" in source
    assert "all external scene-specific providers failed" in source
    assert "create_generic_legal_fallback_image(" not in source
    assert "_generate_zero_cost_editorial_image" not in source


def test_scene_visual_qa_rejection_falls_through_to_external_provider(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from reel_pipeline import _generate_scene_with_provider_fallbacks
    used = []
    def fake_create(**kwargs):
        provider = kwargs["provider"]
        used.append(provider)
        Path(kwargs["output_path"]).write_bytes((provider.encode("ascii") * 6000)[:12000])
    def fake_qa(**kwargs):
        return {"decision": "PASS" if Path(kwargs["image_path"]).read_bytes().startswith(b"wikimedia") else "REGENERATE",
                "issues": ["off-topic generated scene"]}
    result = _generate_scene_with_provider_fallbacks(
        topic="المرفق العام الاقتصادي", post="خدمات المرافق العامة الاقتصادية",
        image_brief="Municipal water treatment plant with tanks and pipes",
        output_path=tmp_path / "scene.jpg", api_key="",
        cloudflare_account_id="", cloudflare_api_token="",
        providers={1:"pollinations",2:"cloudflare",3:"gemini",4:"openverse",5:"wikimedia"},
        create_image=fake_create, qa_image=fake_qa,
    )
    assert used == ["pollinations", "cloudflare", "gemini", "pixabay"]
    assert result["provider"] == "pixabay"
    assert result["qa"]["decision"] == "PASS"


def test_recovery_queue_never_retries_topic_source_mismatch_as_an_image_failure():
    workflow = (ROOT / ".github" / "workflows" / "reel-regenerate-rejected.yml").read_text(encoding="utf-8")
    assert "retryable_legacy_mapping_failure" not in workflow
    assert 'last_error.startswith("REEL_SOURCE_TOPIC_MISMATCH")' not in workflow
    assert "Topic mismatch is a source-integrity failure, not an image-provider" in workflow
    assert "retryable_failure = retryable_image_failure" in workflow


def test_tts_fallback_chain_uses_only_approved_neural_providers(monkeypatch, tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    import reel_pipeline
    calls = []
    def fail_gemini(*args, **kwargs):
        calls.append("gemini")
        raise RuntimeError("429 quota")
    def pass_google(*args, **kwargs):
        calls.append("google")
        return tmp_path / "voice.mp3"
    monkeypatch.setattr(reel_pipeline, "generate_gemini_tts_audio", fail_gemini)
    monkeypatch.setattr(reel_pipeline, "generate_google_cloud_arabic_tts_audio", pass_google)
    result = reel_pipeline.generate_reel_narration_with_fallbacks("key", {}, "نص تجريبي", [], tmp_path / "voice.mp3")
    assert result == tmp_path / "voice.mp3"
    assert calls == ["gemini", "google"]
