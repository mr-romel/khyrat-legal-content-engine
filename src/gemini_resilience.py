from __future__ import annotations

import random
import time
from functools import wraps
from typing import Any, Callable


_RETRYABLE_MARKERS = (
    "503",
    "UNAVAILABLE",
    "429",
    "RESOURCE_EXHAUSTED",
    "RATE_LIMIT",
    "DEADLINE_EXCEEDED",
    "TIMEOUT",
    "TIMED OUT",
    "INTERNAL",
    "SERVICE_UNAVAILABLE",
)


def is_retryable_gemini_error(exc: BaseException) -> bool:
    text = str(exc).upper()
    return any(marker in text for marker in _RETRYABLE_MARKERS)


def with_gemini_retry(
    func: Callable[..., Any],
    *,
    attempts: int = 4,
    initial_delay: float = 4.0,
    max_delay: float = 20.0,
) -> Callable[..., Any]:
    """Retry only transient Gemini/service failures; never duplicate business actions."""
    @wraps(func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        last_error: BaseException | None = None
        for attempt in range(1, attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not is_retryable_gemini_error(exc):
                    raise
                delay = min(max_delay, initial_delay * (2 ** (attempt - 1)))
                delay += random.uniform(0, 1.25)
                print(
                    f"Gemini transient error on attempt {attempt}/{attempts}: {exc}. "
                    f"Retrying in {delay:.1f}s...",
                    flush=True,
                )
                time.sleep(delay)
        assert last_error is not None
        raise last_error

    return wrapped


def patch_client(client: Any) -> Any:
    """Wrap one google-genai Client's text generation call with bounded retry."""
    models = getattr(client, "models", None)
    generate = getattr(models, "generate_content", None)
    if generate is None or getattr(generate, "_khyrat_retry", False):
        return client

    wrapped = with_gemini_retry(generate)
    setattr(wrapped, "_khyrat_retry", True)
    try:
        setattr(models, "generate_content", wrapped)
    except Exception:
        # Some SDK releases expose an immutable models facade. In that case the
        # caller can still use the standalone retry decorator in a future upgrade.
        return client
    return client
