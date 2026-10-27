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


def test_image_generation_failure_never_blocks_social_publication():
    main_source = Path("src/main.py").read_text(encoding="utf-8")
    assert '"Image QA Status": "IMAGE_UNAVAILABLE_TEXT_FALLBACK"' in main_source
    assert "publishing text-only and continuing" in main_source
    assert "No usable image available; continuing with text-only publication" in main_source
    assert "refusing text-only social publication" not in main_source



def test_fallback_reel_uses_fifteen_second_segments_and_single_outro():
    source = Path("src/reel_pipeline.py").read_text(encoding="utf-8")
    assert "segment_seconds = 15.0" in source
    assert "segment_duration = min(segment_seconds, base_duration - (i * segment_seconds))" in source
    assert "branded end-card appended once" in source
    assert "generated/ask mahmoud logo.png" in source
    assert "Original brand logo" in source
    assert "خليك فاكر دايما ... اسأل محمود" in source
    assert "refusing unbranded Reel delivery" in source



def test_primary_and_fallback_reels_are_stitched_into_fifteen_second_segments():
    source = Path("src/reel_pipeline.py").read_text(encoding="utf-8")
    assert "def stitch_video_in_15s_segments(" in source
    assert "segment_seconds = 15.0" in source
    assert "transition=fade:duration=" in source
    assert "segments_stitched=" in source
    assert "stitch_video_in_15s_segments(raw_video, segmented_video)" in source
    assert "stitch_video_in_15s_segments(output_video, segmented_video)" in source
    assert "add_motion_graphics_layer(segmented_video, output_video" in source
