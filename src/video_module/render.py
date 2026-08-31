from __future__ import annotations

import subprocess
from pathlib import Path


def render_vertical(images: list[Path] | Path, audio: Path, output: Path, captions: Path | None = None, logo: Path | None = None) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = images if isinstance(images, list) else [images]
    if not sources:
        raise ValueError("at least one image is required")
    duration = max(3, 1)
    inputs: list[str] = []
    filters: list[str] = []
    for i, image in enumerate(sources):
        inputs += ["-loop", "1", "-t", str(duration), "-i", str(image)]
        filters.append(f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]")
    concat_inputs = "".join(f"[v{i}]" for i in range(len(sources)))
    filters.append(f"{concat_inputs}concat=n={len(sources)}:v=1:a=0[base]")
    current = "base"
    audio_index = len(sources)
    inputs += ["-i", str(audio)]
    if logo:
        inputs += ["-i", str(logo)]
        filters.append(f"[{audio_index+1}:v]format=rgba,scale=300:-1[lg]")
        filters.append(f"[{current}][lg]overlay=W-w-50:50[branded]")
        current = "branded"
    if captions:
        cap = captions.as_posix().replace("\\", "/").replace(":", "\\:")
        filters.append(f"[{current}]subtitles='{cap}'[final]")
        current = "final"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", f"[{current}]", "-map", f"{audio_index}:a:0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)]
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
