from __future__ import annotations

import json
import subprocess
from pathlib import Path


def render_vertical(images: list[Path] | Path, audio: Path, output: Path, captions: Path | None = None, logo: Path | None = None) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = images if isinstance(images, list) else [images]
    if not sources:
        raise ValueError("at least one image is required")

    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(audio)], check=True, text=True, capture_output=True)
    total = float(json.loads(probe.stdout)["format"]["duration"])
    if total < 45:
        raise ValueError(f"Reel audio is too short: {total:.1f}s; expected at least 45s")

    count = min(max(len(sources), 1), 5)
    scene = max(total / count, 1.0)
    transition = min(0.5, max(0.25, scene / 8))
    inputs: list[str] = []
    filters: list[str] = []
    for i, image in enumerate(sources[:count]):
        inputs += ["-loop", "1", "-t", f"{scene + transition:.3f}", "-i", str(image)]
        filters.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v{i}]"
        )

    current = "v0"
    offset = scene - transition
    for i in range(1, count):
        out = f"xf{i}"
        filters.append(f"[{current}][v{i}]xfade=transition=fade:duration={transition:.3f}:offset={max(offset,0):.3f}[{out}]")
        current = out
        offset += scene - transition

    audio_index = count
    inputs += ["-i", str(audio)]

    if logo:
        inputs += ["-i", str(logo)]
        filters.append(f"[{audio_index+1}:v]format=rgba,colorkey=0xFFFFFF:0.08:0.02,scale=360:-1[lg]")
        filters.append(f"[{current}][lg]overlay=W-w-45:45[branded]")
        current = "branded"

    if captions:
        cap = captions.as_posix().replace("\\", "/").replace(":", "\\:")
        style = "FontName=Noto Sans Arabic,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=150,Spacing=0"
        filters.append(f"[{current}]subtitles='{cap}':force_style='{style}'[final]")
        current = "final"

    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", f"[{current}]", "-map", f"{audio_index}:a:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest", str(output),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output


def validate_mp4(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("MP4 missing or empty")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration", "-of", "json", str(path)], check=True, text=True, capture_output=True)
    streams = json.loads(probe.stdout).get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video or not audio_stream:
        raise ValueError("MP4 must contain video and audio streams")
    if video.get("width") != 1080 or video.get("height") != 1920:
        raise ValueError("MP4 must be 1080x1920 (9:16)")
    duration = float(video.get("duration") or audio_stream.get("duration") or 0)
    if duration < 45:
        raise ValueError(f"MP4 duration too short: {duration:.1f}s")
    return {"width": video["width"], "height": video["height"], "video": True, "audio": True, "duration": duration}
