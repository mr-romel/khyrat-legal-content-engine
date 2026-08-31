from __future__ import annotations

import subprocess
from pathlib import Path


def render_vertical(image: Path, audio: Path, output: Path, captions: Path | None = None) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    if captions:
        vf += f",subtitles={captions.as_posix()}"
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(image), "-i", str(audio), "-vf", vf,
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output


def validate_mp4(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("MP4 missing or empty")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration", "-of", "json", str(path)], check=True, text=True, capture_output=True)
    import json
    streams = json.loads(probe.stdout).get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise ValueError("MP4 must contain video and audio streams")
    if video.get("width") != 1080 or video.get("height") != 1920:
        raise ValueError("MP4 must be 1080x1920 (9:16)")
    return {"width": video["width"], "height": video["height"], "video": True, "audio": True}
