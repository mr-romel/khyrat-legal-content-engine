from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


def render_vertical_mp4(audio_path: Path, output_path: Path, *, ffmpeg_bin: str = "ffmpeg") -> Path:
    """Render a simple 9:16 MP4 using FFmpeg; no Core dependencies."""
    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)
    if shutil.which(ffmpeg_bin) is None:
        raise RuntimeError("FFmpeg is not installed")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_bin,
        "-y",
        "-f", "lavfi",
        "-i", "color=c=black:s=1080x1920:r=30",
        "-i", str(audio_path),
        "-shortest",
        "-vf", "format=yuv420p",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(output_path),
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path
