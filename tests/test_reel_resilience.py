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


def test_image_qa_rejection_is_advisory_and_keeps_the_image():
    main_source = Path("src/main.py").read_text(encoding="utf-8")
    assert 'image_qa_status = "QA_WARNING_RETAINED"' in main_source
    assert "image_path.unlink(missing_ok=True)" not in main_source[
        main_source.find('if image_qa_status == "QA_REJECTED"'):
        main_source.find('print(f"IMAGE SEMANTIC QA:')
    ]


def test_image_generation_failure_never_blocks_social_publication():
    main_source = Path("src/main.py").read_text(encoding="utf-8")
    assert 'image_qa_status = "IMAGE_GENERATION_FAILED_TEXT_FALLBACK"' in main_source
    assert "continuing with text publication fallback" in main_source
    assert "publishing text to both platforms instead of cancelling the post" in main_source
    assert "refusing text-only social publication" not in main_source
