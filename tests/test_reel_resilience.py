from __future__ import annotations

import ssl
import time
import urllib.error
from pathlib import Path

import reel_pipeline


def test_urlopen_retries_transient_tls_eof(monkeypatch):
    calls = []
    expected = object()

    def flaky_urlopen(request, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            raise urllib.error.URLError(ssl.SSLEOFError("EOF occurred in violation of protocol"))
        return expected

    monkeypatch.setattr(reel_pipeline.urllib.request, "urlopen", flaky_urlopen)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    result = reel_pipeline._urlopen_with_retry(object(), timeout=5, attempts=3)

    assert result is expected
    assert len(calls) == 2
    assert calls[0][1] == 5


def test_edge_tts_is_completely_disabled_and_google_cloud_is_the_fallback():
    reel_source = Path("src/reel_pipeline.py").read_text(encoding="utf-8").casefold()
    requirements = Path("requirements-reel.txt").read_text(encoding="utf-8").casefold()

    assert "edge_tts" not in reel_source
    assert "edge-tts" not in reel_source
    assert "edge-tts" not in requirements
    assert "generate_edge_arabic_tts_audio" not in reel_source
    assert "generate_reel_narration_with_fallbacks" in reel_source
    assert "generate_google_cloud_arabic_tts_audio" in reel_source
    assert "generate_google_cloud_short_arabic_tts_audio" in reel_source


def test_reel_generation_uses_persistent_qa_approved_scene_image_cache():
    source = Path("src/reel_pipeline.py").read_text(encoding="utf-8")
    assert "REEL_IMAGE_CACHE_DIR" in source
    assert "generated/reel_image_cache" in source
    assert "scene_cache_hit=" in source
    assert "scene_cache_saved=" in source
    assert 'meta.get("qa", {}).get("decision") == "PASS"' in source
    assert 'meta.get("image_sha256") == cached_sha' in source


def test_image_provider_retries_use_longer_backoff_and_extended_timeout():
    source = Path("src/image_generator.py").read_text(encoding="utf-8")
    assert source.count("range(1, 6)") >= 2
    assert source.count("retry {attempt + 1}/5") >= 2
    assert "min(5 * (2 ** (attempt - 1)), 40)" in source
    assert 'REEL_IMAGE_PROVIDER_TIMEOUT_SECONDS", "120"' in source


def test_external_tts_retries_use_longer_exponential_backoff():
    source = Path("src/reel_pipeline.py").read_text(encoding="utf-8")
    assert "attempts: int = 5" in source
    assert "min(3 * (2 ** (attempt - 1)), 45)" in source
    assert "min(3 * (2 ** (attempt - 1)), 30)" in source


def test_image_qa_rejection_regenerates_and_blocks_unverified_images():
    main_source = Path("src/main.py").read_text(encoding="utf-8")
    assert "for image_qa_attempt in range(1, 4)" in main_source
    assert 'image_qa_status = "QA_REJECTED"' in main_source
    assert "IMAGE SEMANTIC QA: rejected attempt" in main_source
    assert "IMAGE SEMANTIC QA: PASS" in main_source
    assert "IMAGE_QA_UNAVAILABLE_BLOCKED" in main_source
    assert "IMAGE_QA_REJECTED_BLOCKED" in main_source
    assert "IMAGE_QA_BLOCKED" in main_source


def test_image_generation_failure_uses_generic_legal_image_and_keeps_publication_image_required():
    main_source = Path("src/main.py").read_text(encoding="utf-8")
    generator_source = Path("src/image_generator.py").read_text(encoding="utf-8")
    assert "create_generic_legal_fallback_image(" in main_source
    assert '"Image QA Status": image_qa_status' in main_source
    assert '"Image Mode": "GENERIC_LEGAL_FALLBACK"' in main_source
    assert "def create_generic_legal_fallback_image(" in generator_source
    assert "brand_published_image(output_path)" in generator_source
    assert "publish_text(" not in main_source
    assert "publish_text_to_linkedin" not in main_source




def test_scheduled_catch_up_processes_every_due_row_and_isolates_failures():
    source = Path("src/run_main.py").read_text(encoding="utf-8")
    assert "KHYRAT_CATCH_UP_ALL_DUE" in source
    assert "selected_rows = sorted(" in source
    assert "for row_number, row in selected_rows:" in source
    assert "CATCH_UP_ROW_FAILED" in source
    assert "continuing with remaining due rows" in source
    assert "CATCH_UP_SUMMARY" in source

def test_remotion_reel_uses_existing_scenes_audio_and_single_branded_outro():
    source = Path("src/reel_pipeline.py").read_text(encoding="utf-8")
    renderer = Path("src/remotion_renderer.py").read_text(encoding="utf-8")
    composition = Path("remotion/src/Reel.tsx").read_text(encoding="utf-8")

    assert "scenes=scenes" in source
    assert "voice_audio=tts_audio" in source
    assert "slogan_audio=slogan_audio" in source
    assert "render_reel_with_remotion(" in source
    assert "scene_props" in renderer
    assert "voiceAudio" in renderer and "sloganAudio" in renderer
    assert "logo" in renderer
    assert "خليك فاكر دايما ... اسأل محمود" in source
    assert "REEL_STAGE renderer=REMOTION" in renderer
    assert "build_fast_fallback_reel(" not in source


def test_remotion_is_the_only_reel_compositor_and_fails_closed():
    source = Path("src/reel_pipeline.py").read_text(encoding="utf-8")
    renderer = Path("src/remotion_renderer.py").read_text(encoding="utf-8")
    composition = Path("remotion/src/Reel.tsx").read_text(encoding="utf-8")

    assert "def stitch_video_in_15s_segments(" not in source
    assert "MoneyPrinterTurbo" not in source
    assert "REMOTION_RENDER_FAILED" in renderer
    assert "REMOTION_OUTPUT_INVALID" in renderer
    assert "raise RuntimeError" in renderer
    assert "Sequence" in composition
    assert "interpolate(" in composition
    assert "Audio" in composition
    assert "subtitles.map" in composition


def test_gemini_array_response_uses_deterministic_reel_fallback(monkeypatch):
    from types import SimpleNamespace

    class FakeModels:
        def generate_content(self, **_kwargs):
            return SimpleNamespace(text='["not", "an", "object"]')

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(reel_pipeline.genai, "Client", lambda **_kwargs: FakeClient())
    monkeypatch.delenv("REEL_SKIP_GEMINI", raising=False)
    post = (
        "المرفق العام الاقتصادي يقدم خدمات أساسية للجمهور من خلال تنظيم مستمر يخضع لقواعد قانونية محددة. "
        "ويجب التمييز بين طبيعة الخدمة العامة والنشاط التجاري الذي تمارسه الشركات الخاصة في السوق. "
        "ويؤثر هذا التمييز على التزامات الجهة القائمة على تشغيل المرفق وعلى حقوق المنتفعين بالخدمة. "
        "كما يجب مراجعة المستندات المنظمة للتشغيل وطبيعة الجهة المختصة قبل اتخاذ أي إجراء قانوني."
    )
    result = reel_pipeline.make_brief("test-key", "test-model", "المرفق العام الاقتصادي", post)
    assert result["generation_mode"] == "deterministic_fallback"
    assert len(result["video_terms"]) == 8


def test_remotion_renderer_resolves_output_path_before_running_from_project_directory():
    source = Path("src/remotion_renderer.py").read_text(encoding="utf-8")
    assert "output_video = output_video.resolve()" in source
    assert "cwd=project_dir" in source


def test_reel_scene_generation_uses_five_distinct_images_and_quota_safe_fallbacks():
    source = Path("src/reel_pipeline.py").read_text(encoding="utf-8")
    image_generator = Path("src/image_generator.py").read_text(encoding="utf-8")
    assert "reel_scene_count = 5" in source
    assert '1: "pollinations"' in source
    assert '2: "cloudflare"' in source
    assert '3: "local_scene"' in source
    assert '4: "wikimedia"' not in source
    assert '5: "pixabay"' not in source
    assert "REEL_SCENE_VISUAL_QA_REJECTED" in source
    assert "create_generic_legal_fallback_image" not in source
    assert "LOCAL_SCENE_ILLUSTRATION" in image_generator


def test_cloudflare_flux2_dev_uses_required_multipart_request_format():
    source = Path("src/image_generator.py").read_text(encoding="utf-8")
    assert "@cf/black-forest-labs/flux-2-dev" in source
    assert "@cf/black-forest-labs/flux-2-klein-9b" in source
    assert "provider_preference == \"cloudflare_klein\"" in source
    assert "files=multipart_fields" in source
    assert "request_fields[\"steps\"]" in source
    assert '"Content-Type": "application/json"' not in source
    assert '"width": str(width)' in source
    assert '"height": str(height)' in source


def test_gemini_image_quota_exhaustion_skips_retries():
    source = Path("src/image_generator.py").read_text(encoding="utf-8")
    assert "Gemini image quota is exhausted; skipping retries" in source
    assert "resource_exhausted" in source


def test_reel_scene_budget_is_five_distinct_images_with_pollinations_primary():
    source = Path("src/reel_pipeline.py").read_text(encoding="utf-8")
    assert "reel_scene_count = 5" in source
    assert "brief[\"video_terms\"][:reel_scene_count]" in source
    assert "if len(scenes) != reel_scene_count" in source
    assert '1: "pollinations"' in source
    assert '2: "cloudflare"' in source
    assert '3: "local_scene"' in source
    assert '4: "wikimedia"' not in source
    assert '5: "pixabay"' not in source


def test_wikimedia_fallback_is_license_checked_and_attributed():
    source = Path("src/image_generator.py").read_text(encoding="utf-8")
    assert "def _generate_with_wikimedia()" in source
    assert "LicenseShortName" in source
    assert "LicenseUrl" in source
    assert "attribution_required" in source
    assert "WIKIMEDIA_COMMONS_SCENE" in source


def test_gemini_script_topic_drift_falls_back_to_approved_post(monkeypatch):
    from types import SimpleNamespace
    import json

    class FakeModels:
        def generate_content(self, **_kwargs):
            employment_script = (
                "يجب على صاحب العمل مراجعة عقد العمل قبل اتخاذ أي قرار يخص الموظفين. "
                "ويجب توثيق ساعات العمل والراتب والإجازات والجزاءات في سجلات واضحة. "
                "ولا يجوز فصل العامل أو تغيير أجره دون سند قانوني صحيح. "
                "ويحتاج الموظف إلى الاحتفاظ بالمراسلات والمستندات التي تثبت حقوقه. "
                "كما يجب مراجعة اللوائح الداخلية وسياسات الموارد البشرية قبل أي إجراء."
            )
            return SimpleNamespace(text=json.dumps({"script": employment_script, "video_terms": []}, ensure_ascii=False))

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(reel_pipeline.genai, "Client", lambda **_kwargs: FakeClient())
    monkeypatch.delenv("REEL_SKIP_GEMINI", raising=False)
    topic = "المرفق العام الاقتصادي — زاوية جديدة: 3 علامات تحذيرية قبل اتخاذ القرار"
    post = (
        "تخيل أنك تدير منشأة اقتصادية تقدم خدمة حيوية للجمهور، وفجأة وجدت نفسك أمام ضغوط لرفع الأسعار "
        "أو تغيير معايير الخدمة بشكل يمس جوهر التزامك، هنا تظهر طبيعة المرفق العام الاقتصادي ككيان محكوم "
        "بقواعد تختلف عن الشركات التجارية العادية، فالمشرع يضع قيوداً تهدف لضمان استمرارية الخدمة وانتظامها. "
        "وقبل أن تتخذ قراراً قد يضعك في مواجهة قانونية، راقب العلامات الثلاث المتعلقة بالالتزام التعاقدي "
        "والأسعار والمواصفات واستمرارية الخدمة، وراجع السند القانوني الذي يربطك بالجهة الإدارية."
    )
    result = reel_pipeline.make_brief("test-key", "test-model", topic, post)
    assert result["generation_mode"] == "deterministic_fallback"
    assert reel_pipeline._visual_topic_family(result["script"]) == "public_utility"


def test_urlopen_does_not_retry_nontransient_http_429(monkeypatch):
    calls = []
    def rate_limited(request, timeout):
        calls.append((request, timeout))
        raise urllib.error.HTTPError("https://example.invalid", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(reel_pipeline.urllib.request, "urlopen", rate_limited)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    try:
        reel_pipeline._urlopen_with_retry(object(), timeout=5, attempts=3)
        assert False, "HTTP 429 must be raised without retries"
    except urllib.error.HTTPError as exc:
        assert exc.code == 429
    assert len(calls) == 1


def test_cloudflare_image_http_429_skips_provider_retries():
    source = Path("src/image_generator.py").read_text(encoding="utf-8")
    assert 'if response.status_code == 429:' in source
    assert "skipping retries and switching to the next provider" in source


def test_reel_pipeline_uses_actual_provider_returned_audio_paths():
    source = Path("src/reel_pipeline.py").read_text(encoding="utf-8")
    assert "tts_audio = generate_reel_narration_with_fallbacks(" in source
    assert "fit_reel_narration_duration(tts_audio" in source
    assert "slogan_audio = generate_short_signoff_with_fallbacks(" in source
    assert "slogan_audio=slogan_audio" in source
