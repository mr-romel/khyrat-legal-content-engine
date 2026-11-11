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


def test_edge_tts_is_not_a_dependency_or_fallback():
    reel_source = Path("src/reel_pipeline.py").read_text(encoding="utf-8").casefold()
    requirements = Path("requirements-worker.txt").read_text(encoding="utf-8").casefold()

    assert "edge_tts" not in reel_source
    assert "edge-tts" not in reel_source
    assert "edge-tts" not in requirements


def test_image_qa_rejection_regenerates_and_blocks_unverified_images():
    main_source = Path("src/main.py").read_text(encoding="utf-8")
    assert "for image_qa_attempt in range(1, 4)" in main_source
    assert 'image_qa_status = "QA_REJECTED"' in main_source
    assert "IMAGE SEMANTIC QA: rejected attempt" in main_source
    assert "IMAGE SEMANTIC QA: PASS" in main_source
    assert "valid generated image accepted" in main_source


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


def test_reel_scene_generation_uses_three_distinct_providers_and_never_generic_placeholders():
    source = Path("src/reel_pipeline.py").read_text(encoding="utf-8")
    image_generator = Path("src/image_generator.py").read_text(encoding="utf-8")
    assert 'visual_providers = {1: "cloudflare", 2: "gemini", 3: "pixabay"}' in source
    assert "REEL_SCENE_VISUAL_QA_FAILED" in source
    assert "create_generic_legal_fallback_image" not in source
    assert '"pixabay"' in image_generator
    assert "scene_tokens" in image_generator
