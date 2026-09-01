from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Protocol


class TTSProvider(Protocol):
    def synthesize(self, text: str, output_path: Path) -> Path: ...


class LahgtnaChatterboxProvider:
    """Egyptian-Arabic TTS using Lahgtna/Chatterbox v1 with expressive delivery."""

    def synthesize(self, text: str, output_path: Path) -> Path:
        import tempfile

        repo = Path(tempfile.gettempdir()) / "lahgtna-chatterbox"
        if not repo.exists():
            subprocess.run(
                ["git", "clone", "--depth", "1", "https://github.com/Oddadmix/lahgtna-chatterbox.git", str(repo)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                ["python", "-m", "pip", "install", "-r", str(repo / "requirments.txt")],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wav = output_path.with_suffix(".wav")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo / "src") + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run(
            [
                "python", str(repo / "src" / "inference.py"),
                "--text", text,
                "--dialect", "eg",
                "--exaggeration", "0.68",
                "--temperature", "0.72",
                "--cfg-weight", "0.32",
                "--output", str(wav),
            ],
            check=True,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        # Gentle mastering only: consistent loudness and headroom, without
        # changing pitch, timing, or the speaker character.
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(wav),
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=7",
                "-codec:a", "libmp3lame", "-q:a", "3", str(output_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError("Egyptian TTS produced no audio")
        return output_path


class EdgeTTSProvider:
    """Optional fallback only; production prefers Egyptian Lahgtna."""

    def __init__(self, voice: str = "ar-EG-ShakirNeural") -> None:
        self.voice = voice

    def synthesize(self, text: str, output_path: Path) -> Path:
        import asyncio
        import edge_tts
        output_path.parent.mkdir(parents=True, exist_ok=True)

        async def _run() -> None:
            await edge_tts.Communicate(text, self.voice).save(str(output_path))

        asyncio.run(_run())
        return output_path


def synthesize_with_fallback(text: str, output_path: Path, providers: list[TTSProvider]) -> Path:
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
