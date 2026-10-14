from __future__ import annotations

"""Small provider router for text generation.

Order: Gemini first, then Groq, Cerebras, and OpenRouter when their API keys
are configured. Alternative providers are optional; their free quotas are
controlled by each provider and are not guaranteed to be unlimited.
"""
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import requests
from google import genai


_TRANSIENT = {408, 425, 429, 500, 502, 503, 504}
_GEMINI_QUOTA_EXHAUSTED = False


def has_any_provider_key() -> bool:
    return any(os.getenv(name, "").strip() for name in (
        "GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY"
    ))


def _status(exc: Exception) -> int | None:
    for obj in (exc, getattr(exc, "response", None)):
        if obj is None:
            continue
        for attr in ("status_code", "status", "code"):
            try:
                value = getattr(obj, attr, None)
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                pass
    match = re.search(r"\b(?:HTTP\s*)?(408|425|429|500|502|503|504)\b", str(exc))
    return int(match.group(1)) if match else None


def _is_quota(exc: Exception) -> bool:
    value = str(exc).casefold()
    return _status(exc) == 429 or any(token in value for token in (
        "resource_exhausted", "quota exceeded", "daily limit", "rate limit"
    ))


def _prompt_text(contents: Any) -> str:
    if isinstance(contents, str):
        return contents
    if isinstance(contents, (list, tuple)):
        pieces = []
        for item in contents:
            text = getattr(item, "text", None)
            pieces.append(str(text if text is not None else item))
        return "\n".join(pieces)
    return str(contents or "")


@dataclass
class TextResponse:
    text: str


class _Models:
    def __init__(self, router: "RoutedClient"):
        self.router = router

    def generate_content(self, *, model: str, contents: Any, config: Any = None, **kwargs: Any) -> TextResponse:
        return TextResponse(self.router.generate(_prompt_text(contents), model=model, config=config))


class _Chat:
    def __init__(self, router: "RoutedClient", model: str):
        self.router, self.model = router, model

    def send_message(self, message: Any, config: Any = None, **kwargs: Any) -> TextResponse:
        return TextResponse(self.router.generate(_prompt_text(message), model=self.model, config=config))


class _Chats:
    def __init__(self, router: "RoutedClient"):
        self.router = router

    def create(self, *, model: str, **kwargs: Any) -> _Chat:
        return _Chat(self.router, model)


class RoutedClient:
    def __init__(self, api_key: str = ""):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.models = _Models(self)
        self.chats = _Chats(self)

    @staticmethod
    def _config_value(config: Any, name: str, default: Any = None) -> Any:
        if config is None:
            return default
        if isinstance(config, dict):
            return config.get(name, default)
        return getattr(config, name, default)

    def _generate_gemini(self, prompt: str, model: str, config: Any) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        return text

    def _generate_openai_compatible(self, provider: str, prompt: str, model: str, config: Any) -> str:
        settings = {
            "groq": (
                os.getenv("GROQ_API_KEY", "").strip(),
                os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
                "https://api.groq.com/openai/v1/chat/completions",
            ),
            "cerebras": (
                os.getenv("CEREBRAS_API_KEY", "").strip(),
                os.getenv("CEREBRAS_MODEL", "llama-3.3-70b").strip(),
                "https://api.cerebras.ai/v1/chat/completions",
            ),
            "openrouter": (
                os.getenv("OPENROUTER_API_KEY", "").strip(),
                os.getenv("OPENROUTER_MODEL", "openrouter/free").strip(),
                "https://openrouter.ai/api/v1/chat/completions",
            ),
        }
        key, selected_model, endpoint = settings[provider]
        if not key:
            raise RuntimeError(f"{provider} API key is not configured.")
        if provider == "openrouter" and os.getenv("OPENROUTER_MODEL", "").strip():
            selected_model = os.getenv("OPENROUTER_MODEL", "").strip()
        elif model and model.startswith(provider + "/"):
            selected_model = model.split("/", 1)[1]
        max_tokens = self._config_value(config, "max_output_tokens", 4096)
        if not isinstance(max_tokens, int):
            max_tokens = 4096
        payload = {
            "model": selected_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max(256, min(max_tokens, 8192)),
            "temperature": 0.6,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/mr-romel/khyrat-legal-content-engine"
            headers["X-Title"] = "Khyrat Legal Content Engine"
        response = requests.post(endpoint, headers=headers, json=payload, timeout=90)
        if response.status_code >= 400:
            detail = response.text[:600]
            raise RuntimeError(f"{provider} HTTP {response.status_code}: {detail}")
        data = response.json()
        choices = data.get("choices") or []
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        if isinstance(content, list):
            content = "".join(str(item.get("text", "") if isinstance(item, dict) else item) for item in content)
        result = str(content or "").strip()
        if not result:
            raise RuntimeError(f"{provider} returned an empty response.")
        return result

    def generate(self, prompt: str, *, model: str, config: Any = None) -> str:
        global _GEMINI_QUOTA_EXHAUSTED
        failures: list[str] = []
        providers = []
        if self.api_key and not _GEMINI_QUOTA_EXHAUSTED:
            providers.append(("Gemini", lambda: self._generate_gemini(prompt, model, config)))
        for provider in ("groq", "cerebras", "openrouter"):
            key_name = {"groq": "GROQ_API_KEY", "cerebras": "CEREBRAS_API_KEY", "openrouter": "OPENROUTER_API_KEY"}[provider]
            if os.getenv(key_name, "").strip():
                providers.append((provider, lambda p=provider: self._generate_openai_compatible(p, prompt, model, config)))
        for name, call in providers:
            try:
                result = call()
                if name != "Gemini":
                    print(f"AI provider fallback selected: {name}")
                return result
            except Exception as exc:
                failures.append(f"{name}: {type(exc).__name__} ({_status(exc) or 'no HTTP status'})")
                if name == "Gemini" and _is_quota(exc):
                    _GEMINI_QUOTA_EXHAUSTED = True
                    print("Gemini quota/rate limit detected; switching to configured alternate AI providers for this worker run.")
                    continue
                if _status(exc) in _TRANSIENT or isinstance(exc, (requests.Timeout, requests.ConnectionError)):
                    print(f"AI provider {name} unavailable; trying the next configured provider.")
                    continue
                # Authentication, model, and request errors should not be hidden by a silent cascade.
                if name != "Gemini":
                    print(f"AI provider {name} request failed; trying next configured provider.")
                    continue
                raise
        raise RuntimeError("All configured text AI providers failed or are out of quota. " + " | ".join(failures))


def create_client(api_key: str = "") -> RoutedClient:
    return RoutedClient(api_key=api_key)
