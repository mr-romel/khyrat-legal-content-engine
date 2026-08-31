from __future__ import annotations

import asyncio
from pathlib import Path


def _fmt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(text: str, output: Path, duration: float) -> Path:
    words = text.split()
    if not words or duration <= 0:
        raise ValueError("Caption source and duration are required")
    chunk = 6
    groups = [words[i:i + chunk] for i in range(0, len(words), chunk)]
    step = duration / len(groups)
    lines = []
    for i, group in enumerate(groups):
        start = i * step
        end = min(duration, (i + 1) * step)
        lines += [str(i + 1), f"{_fmt(start)} --> {_fmt(end)}", " ".join(group), ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def caption_from_tts(text: str, audio: Path, output: Path) -> Path:
    import subprocess, json
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(audio)], check=True, text=True, capture_output=True)
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    return write_srt(text, output, duration)
