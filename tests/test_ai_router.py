from __future__ import annotations

import ai_router


class _Response:
    status_code = 200
    text = ""

    def __init__(self, content="fallback answer"):
        self.content = content

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


def test_gemini_quota_routes_to_groq(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
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
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "MODEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert ai_router.has_any_provider_key() is False


def test_openai_compatible_request_preserves_json_and_generation_settings(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    captured = {}

    def fake_post(endpoint, *, headers, json, timeout):
        captured["endpoint"] = endpoint
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response('{"answer": "ok"}')

    monkeypatch.setattr(ai_router.requests, "post", fake_post)
    router = ai_router.RoutedClient()
    config = {
        "system_instruction": "You are a careful editor.",
        "response_mime_type": "application/json",
        "max_output_tokens": 1800,
        "temperature": 0.1,
        "top_p": 0.8,
    }
    result = router._generate_openai_compatible(
        "groq", "Make a JSON answer", "gemini-model", config
    )

    assert result == '{"answer": "ok"}'
    payload = captured["json"]
    assert payload["messages"] == [
        {"role": "system", "content": "You are a careful editor."},
        {"role": "user", "content": "Make a JSON answer"},
    ]
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 1800
    assert payload["temperature"] == 0.1
    assert payload["top_p"] == 0.8


def test_openrouter_is_pinned_to_free_model_even_if_overridden(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")
    monkeypatch.setenv("OPENROUTER_MODEL", "provider/paid-model")
    captured = {}

    def fake_post(endpoint, *, headers, json, timeout):
        captured["endpoint"] = endpoint
        captured["json"] = json
        return _Response()

    monkeypatch.setattr(ai_router.requests, "post", fake_post)
    router = ai_router.RoutedClient()
    assert router._generate_openai_compatible(
        "openrouter", "test prompt", "openrouter/paid-model", None
    ) == "fallback answer"
    assert captured["json"]["model"] == "openrouter/free"


def test_fallback_refuses_to_drop_google_search_tool(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    router = ai_router.RoutedClient()
    try:
        router._generate_openai_compatible(
            "groq",
            "Research this legal issue",
            "gemini-model",
            {"tools": [{"google_search": {}}]},
        )
    except RuntimeError as exc:
        assert "cannot preserve Gemini-only tools" in str(exc)
    else:
        raise AssertionError("Fallback must not silently discard Google Search tools")


def test_non_quota_gemini_error_also_uses_configured_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(ai_router, "_GEMINI_QUOTA_EXHAUSTED", False)
    router = ai_router.RoutedClient(api_key="test-gemini")

    def invalid_model(prompt, model, config):
        raise RuntimeError("invalid model")

    monkeypatch.setattr(router, "_generate_gemini", invalid_model)
    monkeypatch.setattr(
        router, "_generate_openai_compatible", lambda *args, **kwargs: "fallback result"
    )
    assert router.generate("prompt", model="gemini-invalid") == "fallback result"



def test_auxiliary_task_uses_backups_before_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")
    monkeypatch.setattr(ai_router, "_GEMINI_QUOTA_EXHAUSTED", False)
    router = ai_router.RoutedClient(api_key="test-gemini", task="comments")
    calls = []

    def backup(provider, prompt, model, config):
        calls.append(provider)
        return "backup result"

    def gemini(prompt, model, config):
        calls.append("Gemini")
        return "gemini result"

    monkeypatch.setattr(router, "_generate_openai_compatible", backup)
    monkeypatch.setattr(router, "_generate_gemini", gemini)
    assert router.generate("comment prompt", model="gemini-test") == "backup result"
    assert calls == ["groq"]


def test_auxiliary_task_uses_gemini_only_after_all_backups_fail(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")
    monkeypatch.setattr(ai_router, "_GEMINI_QUOTA_EXHAUSTED", False)
    router = ai_router.RoutedClient(api_key="test-gemini", task="image_description")
    calls = []

    def backup(provider, prompt, model, config):
        calls.append(provider)
        raise RuntimeError(f"{provider} temporarily unavailable")

    def gemini(prompt, model, config):
        calls.append("Gemini")
        return "gemini result"

    monkeypatch.setattr(router, "_generate_openai_compatible", backup)
    monkeypatch.setattr(router, "_generate_gemini", gemini)
    assert router.generate("scene prompt", model="gemini-test") == "gemini result"
    assert calls == ["groq", "openrouter", "Gemini"]



def test_meta_model_api_uses_official_endpoint_and_model(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "test-meta-model")
    monkeypatch.delenv("META_MODEL", raising=False)
    captured = {}

    def fake_post(endpoint, *, headers, json, timeout):
        captured["endpoint"] = endpoint
        captured["headers"] = headers
        captured["json"] = json
        return _Response("Meta backup result")

    monkeypatch.setattr(ai_router.requests, "post", fake_post)
    router = ai_router.RoutedClient()
    result = router._generate_openai_compatible(
        "meta", "test prompt", "gemini-model", {"temperature": 0.2}
    )

    assert result == "Meta backup result"
    assert captured["endpoint"] == "https://api.meta.ai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-meta-model"
    assert captured["json"]["model"] == "muse-spark-1.3"
    assert captured["json"]["messages"] == [{"role": "user", "content": "test prompt"}]


def test_meta_model_api_is_last_auxiliary_backup_before_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("MODEL_API_KEY", "test-meta-model")
    monkeypatch.setattr(ai_router, "_GEMINI_QUOTA_EXHAUSTED", False)
    router = ai_router.RoutedClient(api_key="test-gemini", task="comments")
    calls = []

    def meta(provider, prompt, model, config):
        calls.append(provider)
        return "Meta backup result"

    monkeypatch.setattr(router, "_generate_openai_compatible", meta)
    monkeypatch.setattr(router, "_generate_gemini", lambda *args, **kwargs: calls.append("Gemini") or "Gemini result")
    assert router.generate("comment prompt", model="gemini-test") == "Meta backup result"
    assert calls == ["meta"]
