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


def test_transient_image_qa_outage_does_not_downgrade_post_to_text_only():
    main_source = Path("src/main.py").read_text(encoding="utf-8")
    assert 'image_qa_status = "QA_UNAVAILABLE_IMAGE_RETAINED"' in main_source
    assert "Required image generation failed; social publication blocked" in main_source
    assert "refusing text-only social publication" in main_source
