from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TTSProvider(Protocol):
    def synthesize(self, text: str, output_path: Path) -> Path: ...


class EdgeTTSProvider:
    """Edge TTS adapter; imported only when the provider is actually used."""

    def __init__(self, voice: str = "ar-EG-ShakirNeural") -> None:
        self.voice = voice

    def synthesize(self, text: str, output_path: Path) -> Path:
        import asyncio
        import edge_tts

        output_path.parent.mkdir(parents=True, exist_ok=True)

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(str(output_path))

        asyncio.run(_run())
        return output_path


def synthesize_with_fallback(text: str, output_path: Path, providers: list[TTSProvider]) -> Path:
    """Try providers in order. Provider failures stay inside the video boundary."""
    last_error: Exception | None = None
    for provider in providers:
        try:
            result = provider.synthesize(text, output_path)
            if result.is_file() and result.stat().st_size > 0:
                return result
        except Exception as exc:
            last_error = exc
    if last_error:
        raise RuntimeError("All configured TTS providers failed") from last_error
    raise RuntimeError("No TTS provider configured")
