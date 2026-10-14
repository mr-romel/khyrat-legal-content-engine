from __future__ import annotations

"""Text-generation router.

Order: Gemini first, then Groq, Cerebras, and OpenRouter when configured.
Fallback providers are OpenAI-compatible text APIs; they cannot reproduce
Gemini-only tools such as Google Search grounding or multimodal image input.
Their free quotas are provider-controlled and are not guaranteed unlimited.
"""
import os
import re
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
    match = re.search(r"\b(?:HTTP\s*)?(400|401|403|404|408|413|422|425|429|500|502|503|504)\b", str(exc))
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
    # Core legal reasoning stays Gemini-first. Repetitive low-risk tasks use the
    # configured economical providers first, then fall back to Gemini if needed.
    AUXILIARY_TASKS = {"comments", "image_description", "metadata"}

    def __init__(self, api_key: str = "", task: str = "core"):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.task = (task or "core").strip().casefold()
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
                os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip(),
                "https://api.groq.com/openai/v1/chat/completions",
            ),
            "cerebras": (
                os.getenv("CEREBRAS_API_KEY", "").strip(),
                os.getenv("CEREBRAS_MODEL", "gpt-oss-120b").strip(),
                "https://api.cerebras.ai/v1/chat/completions",
            ),
            "openrouter": (
                os.getenv("OPENROUTER_API_KEY", "").strip(),
                os.getenv("OPENROUTER_MODEL", "openrouter/free").strip(),
                "https://openrouter.ai/api/v1/chat/completions",
            ),
        }
        if provider not in settings:
            raise RuntimeError(f"Unknown AI provider: {provider}")
        key, selected_model, endpoint = settings[provider]
        if not key:
            raise RuntimeError(f"{provider} API key is not configured.")
        if model and model.startswith(provider + "/"):
            selected_model = model.split("/", 1)[1]

        tools = self._config_value(config, "tools", None)
        if tools:
            # Do not silently drop provider-specific tools (notably Google Search).
            raise RuntimeError(
                f"{provider} fallback cannot preserve Gemini-only tools from this request; "
                "retry with a provider that supports the required tool/grounding."
            )

        system_instruction = self._config_value(config, "system_instruction", None)
        messages = []
        if system_instruction:
            system_text = _prompt_text(system_instruction)
            if system_text.strip():
                messages.append({"role": "system", "content": system_text})
        messages.append({"role": "user", "content": prompt})

        max_tokens = self._config_value(config, "max_output_tokens", 4096)
        try:
            max_tokens = int(max_tokens)
        except (TypeError, ValueError):
            max_tokens = 4096
        payload: dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "max_tokens": max(256, min(max_tokens, 8192)),
        }
        temperature = self._config_value(config, "temperature", 0.6)
        if temperature is not None:
            try:
                payload["temperature"] = float(temperature)
            except (TypeError, ValueError):
                pass
        top_p = self._config_value(config, "top_p", None)
        if top_p is not None:
            try:
                payload["top_p"] = float(top_p)
            except (TypeError, ValueError):
                pass
        stop_sequences = self._config_value(config, "stop_sequences", None)
        if isinstance(stop_sequences, (list, tuple)) and stop_sequences:
            payload["stop"] = [str(value) for value in stop_sequences]

        response_mime_type = str(self._config_value(config, "response_mime_type", "") or "").lower()
        if response_mime_type == "application/json":
            # All three services expose OpenAI-compatible JSON-object mode.
            payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/mr-romel/khyrat-legal-content-engine"
            headers["X-Title"] = "Khyrat Legal Content Engine"
        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=90)
        except requests.RequestException:
            raise
        if response.status_code >= 400:
            # Keep response details short; never include request headers or API keys.
            detail = str(getattr(response, "text", "") or "")[:600]
            raise RuntimeError(f"{provider} HTTP {response.status_code}: {detail}")
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"{provider} returned invalid JSON from its API.") from exc
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
        configured_alternates = []
        for provider in ("groq", "cerebras", "openrouter"):
            key_name = {
                "groq": "GROQ_API_KEY",
                "cerebras": "CEREBRAS_API_KEY",
                "openrouter": "OPENROUTER_API_KEY",
            }[provider]
            if os.getenv(key_name, "").strip():
                configured_alternates.append(
                    (provider, lambda p=provider: self._generate_openai_compatible(p, prompt, model, config))
                )

        gemini = []
        if self.api_key and not _GEMINI_QUOTA_EXHAUSTED:
            gemini.append(("Gemini", lambda: self._generate_gemini(prompt, model, config)))

        if self.task in self.AUXILIARY_TASKS:
            # Preserve Gemini capacity for original legal drafting and legal review.
            # Auxiliary providers are attempted first; Gemini remains a last resort.
            providers.extend(configured_alternates)
            providers.extend(gemini)
        else:
            providers.extend(gemini)
            providers.extend(configured_alternates)

        for name, call in providers:
            try:
                result = call()
                if name != "Gemini":
                    print(f"AI provider fallback selected: {name}")
                return result
            except Exception as exc:
                status = _status(exc)
                failures.append(f"{name}: {type(exc).__name__} ({status or 'no HTTP status'})")
                if name == "Gemini" and _is_quota(exc):
                    _GEMINI_QUOTA_EXHAUSTED = True
                    print("Gemini quota/rate limit detected; switching to configured alternate AI providers for this worker run.")
                elif name == "Gemini":
                    print(f"Gemini request failed ({status or 'no HTTP status'}); trying configured alternate providers.")
                else:
                    print(f"AI provider {name} unavailable; trying the next configured provider.")

        raise RuntimeError(
            "All configured text AI providers failed or could not support this request. "
            + " | ".join(failures)
        )


def create_client(api_key: str = "", *, task: str = "core") -> RoutedClient:
    """Create a router with task-aware provider order.

    core: Gemini -> Groq -> Cerebras -> OpenRouter
    auxiliary tasks: Groq -> Cerebras -> OpenRouter -> Gemini
    """
    return RoutedClient(api_key=api_key, task=task)
