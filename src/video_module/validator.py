from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


def validate_mp4(path: Path, *, ffprobe_bin: str = "ffprobe") -> dict[str, str]:
    """Validate existence, non-empty output, MP4 container, and 9:16 dimensions."""
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("MP4 is missing or empty")
    if shutil.which(ffprobe_bin) is None:
        raise RuntimeError("ffprobe is not installed")

    command = [
        ffprobe_bin, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,duration",
        "-of", "default=noprint_wrappers=1:nokey=0", str(path),
    ]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    data: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key] = value
    if data.get("width") != "1080" or data.get("height") != "1920":
        raise ValueError("Video is not 1080x1920 vertical format")
    return data
