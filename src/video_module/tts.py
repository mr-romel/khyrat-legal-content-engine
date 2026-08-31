from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TTSProvider(Protocol):
    def synthesize(self, text: str, output_path: Path) -> Path: ...


def synthesize_with_fallback(text: str, output_path: Path, providers: list[TTSProvider]) -> Path:
    """Try providers in order. Provider failures stay inside the video boundary."""
    last_error: Exception | None = None
    for provider in providers:
        try:
            result = provider.synthesize(text, output_path)
            if result.is_file() and result.stat().st_size > 0:
                return result
        except Exception as exc:  # external provider boundary
            last_error = exc
    if last_error:
        raise RuntimeError("All configured TTS providers failed") from last_error
    raise RuntimeError("No TTS provider configured")
