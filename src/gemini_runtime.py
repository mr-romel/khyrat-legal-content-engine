from __future__ import annotations

import os
import re
import time
from typing import Any, Callable

import gemini as _gemini


DEFAULT_FALLBACK_MODEL = "gemini-2.5-flash"
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}
PRIMARY_ATTEMPTS = 3
FALLBACK_ATTEMPTS = 2
INITIAL_BACKOFF_SECONDS = 5.0


def _status_code(exc: Exception) -> int | None:
    for obj in (
        exc,
        getattr(exc, "response", None),
        getattr(exc, "resp", None),
    ):
        if obj is None:
            continue
        for name in ("status_code", "status", "code"):
            value = getattr(obj, name, None)
            try:
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                pass

    match = re.search(r"\b(?:HTTP\s*)?(408|429|500|502|503|504)\b", str(exc))
    return int(match.group(1)) if match else None


def _is_transient(exc: Exception) -> bool:
    return _status_code(exc) in TRANSIENT_STATUS_CODES


def _run_attempts(
    fn: Callable[..., dict[str, Any]],
    kwargs: dict[str, Any],
    *,
    label: str,
    attempts: int,
) -> dict[str, Any]:
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return fn(**kwargs)
        except Exception as exc:
            last_exc = exc
            status = _status_code(exc)
            if not _is_transient(exc) or attempt >= attempts:
                raise

            delay = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(
                f"Gemini {label} temporary error ({status}); "
                f"retry {attempt}/{attempts - 1} in {delay:.0f}s..."
            )
            time.sleep(delay)

    raise RuntimeError("Gemini retry loop ended unexpectedly.") from last_exc


def generate_post(**kwargs: Any) -> dict[str, Any]:
    """Reliable wrapper around the existing content generator.

    Keeps the existing prompt/validation logic intact while adding retries and
    a fallback model for transient provider overloads.
    """
    primary_model = str(kwargs.get("model") or "").strip()
    fallback_model = (
        os.getenv("GEMINI_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL).strip()
        or DEFAULT_FALLBACK_MODEL
    )

    try:
        return _run_attempts(
            _gemini.generate_post,
            kwargs,
            label=f"primary model {primary_model or 'default'}",
            attempts=PRIMARY_ATTEMPTS,
        )
    except Exception as primary_exc:
        if not _is_transient(primary_exc):
            raise

        if not fallback_model or fallback_model == primary_model:
            raise

        fallback_kwargs = dict(kwargs)
        fallback_kwargs["model"] = fallback_model
        print(
            f"Gemini primary model remained unavailable; switching to fallback model {fallback_model}."
        )

        return _run_attempts(
            _gemini.generate_post,
            fallback_kwargs,
            label=f"fallback model {fallback_model}",
            attempts=FALLBACK_ATTEMPTS,
        )
