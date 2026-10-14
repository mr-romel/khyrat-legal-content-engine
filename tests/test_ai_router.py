from __future__ import annotations

import os

import ai_router


class _Response:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": "fallback answer"}}]}


def test_gemini_quota_routes_to_groq(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(ai_router, "_GEMINI_QUOTA_EXHAUSTED", False)
    router = ai_router.RoutedClient(api_key="test-gemini")

    def quota_error(prompt, model, config):
        raise RuntimeError("HTTP 429 RESOURCE_EXHAUSTED quota exceeded")

    monkeypatch.setattr(router, "_generate_gemini", quota_error)
    monkeypatch.setattr(ai_router.requests, "post", lambda *args, **kwargs: _Response())
    assert router.generate("test prompt", model="gemini-test") == "fallback answer"
    assert ai_router._GEMINI_QUOTA_EXHAUSTED is True


def test_no_fallback_key_does_not_claim_alternate_provider(monkeypatch):
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert ai_router.has_any_provider_key() is False
