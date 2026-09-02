from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def _fmt(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h}:{m:02d}:{s:02d},{ms:03d}"


def _clean_word(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def write_srt(text: str, output: Path, duration: float) -> Path:
    words = text.split()
    if not words or duration <= 0:
        raise ValueError("Caption source and duration are required")
    groups = [words[i:i + 6] for i in range(0, len(words), 6)]
    step = duration / len(groups)
    lines = []
    for i, group in enumerate(groups):
        start = i * step
        end = min(duration, (i + 1) * step)
        lines += [str(i + 1), f"{_fmt(start)} --> {_fmt(end)}", " ".join(group), ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _write_chunk_timed_srt(timing_path: Path, output: Path, duration: float) -> Path:
    raw = json.loads(timing_path.read_text(encoding="utf-8"))
    entries: list[tuple[float, float, str]] = []
    cursor = 0.0
    for item in raw:
        caption = _clean_word(str(item.get("text", "")))
        chunk_duration = float(item.get("duration", 0.0) or 0.0)
        if not caption or chunk_duration <= 0:
            continue
        end = min(duration, cursor + chunk_duration)
        entries.append((cursor, end, caption))
        cursor = end
    if not entries:
        raise ValueError("Lahgtna chunk timing data is empty")

    # The audio is assembled from these exact chunks in the same order. Each
    # caption therefore occupies the exact duration of the audio chunk that
    # spoke it, eliminating the old proportional whole-audio drift.
    if cursor < duration:
        start, end, caption = entries[-1]
        entries[-1] = (start, duration, caption)

    lines: list[str] = []
    for number, (start, end, caption) in enumerate(entries, 1):
        lines += [str(number), f"{_fmt(start)} --> {_fmt(end)}", caption, ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _write_timed_srt(text: str, timing_path: Path, output: Path, duration: float) -> Path:
    raw = json.loads(timing_path.read_text(encoding="utf-8"))
    timings = [item for item in raw if _clean_word(str(item.get("text", "")))]
    words = text.split()
    if not timings or not words:
        raise ValueError("Edge TTS timing data is empty")

    count = min(len(words), len(timings))
    if count < max(3, int(len(words) * 0.75)):
        raise ValueError(f"Edge TTS timing mismatch: script_words={len(words)} timed_words={len(timings)}")

    entries: list[tuple[float, float, str]] = []
    index = 0
    max_words_per_caption = 6
    max_caption_seconds = 3.8
    while index < count:
        start = int(timings[index].get("offset_100ns", 0)) / 10_000_000
        end_index = index
        while end_index + 1 < count and end_index - index + 1 < max_words_per_caption:
            candidate_end = int(timings[end_index + 1].get("offset_100ns", 0)) / 10_000_000
            if candidate_end - start > max_caption_seconds:
                break
            end_index += 1
        last = timings[end_index]
        end = (int(last.get("offset_100ns", 0)) + int(last.get("duration_100ns", 0))) / 10_000_000
        end = max(end, start + 0.35)
        entries.append((max(0.0, start), min(duration, end), " ".join(words[index:end_index + 1])))
        index = end_index + 1

    if index < len(words):
        start = entries[-1][1] if entries else 0.0
        entries.append((start, duration, " ".join(words[index:])))

    lines: list[str] = []
    for number, (start, end, caption) in enumerate(entries, 1):
        if end <= start:
            end = min(duration, start + 0.5)
        lines += [str(number), f"{_fmt(start)} --> {_fmt(end)}", caption, ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def caption_from_tts(text: str, audio: Path, output: Path) -> Path:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(audio)],
        check=True, text=True, capture_output=True,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])

    chunk_timing_path = audio.with_suffix(".chunks.json")
    if chunk_timing_path.is_file():
        try:
            return _write_chunk_timed_srt(chunk_timing_path, output, duration)
        except Exception as exc:
            print(f"CAPTION_CHUNK_TIMING_FALLBACK={type(exc).__name__}: {exc}")

    timing_path = audio.with_suffix(".words.json")
    if timing_path.is_file():
        try:
            return _write_timed_srt(text, timing_path, output, duration)
        except Exception as exc:
            print(f"CAPTION_TIMING_FALLBACK={type(exc).__name__}: {exc}")
    return write_srt(text, output, duration)
