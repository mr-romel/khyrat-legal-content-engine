from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _prepare_logo(logo: Path, work: Path) -> Path:
    prepared = work / "logo_transparent.png"
    from PIL import Image
    image = Image.open(logo).convert("RGBA")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            whiteness = min(r, g, b)
            if whiteness >= 245:
                pixels[x, y] = (r, g, b, 0)
            elif whiteness >= 225:
                pixels[x, y] = (r, g, b, int(a * (255 - whiteness) / 30))
    image.save(prepared)
    return prepared


def _ass_time(value: str) -> str:
    value = value.replace(",", ".")
    h, m, rest = value.split(":")
    if "." in rest:
        s, ms = rest.split(".", 1)
    else:
        s, ms = rest, "0"
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{int(ms[:2]):02d}"


def _srt_to_ass(srt: Path, work: Path) -> Path:
    ass = work / "captions_safe_third.ass"
    lines = srt.read_text(encoding="utf-8-sig").replace("\r\n", "\n").split("\n")
    events: list[str] = []
    i = 0
    while i < len(lines):
        if not lines[i].strip().isdigit():
            i += 1
            continue
        i += 1
        if i >= len(lines) or "-->" not in lines[i]:
            continue
        start, end = [x.strip() for x in lines[i].split("-->", 1)]
        i += 1
        text_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i].strip())
            i += 1
        if text_lines:
            text = "\\N".join(text_lines).replace("{", "\\{").replace("}", "\\}")
            events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}")
        i += 1
    ass.write_text(
        """[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,Noto Sans Arabic,36,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,1,0,0,0,100,100,0,2,1,2,0,2,70,70,240,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n""" + "\n".join(events) + "\n", encoding="utf-8")
    return ass


def render_vertical(images: list[Path] | Path, audio: Path, output: Path, captions: Path | None = None, logo: Path | None = None, animated: bool = False) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = images if isinstance(images, list) else [images]
    sources = [Path(p) for p in sources if Path(p).is_file()]
    if not sources:
        raise ValueError("at least one image is required")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(audio)], check=True, text=True, capture_output=True)
    total = float(json.loads(probe.stdout)["format"]["duration"])
    if total < 45:
        raise ValueError(f"Reel audio is too short: {total:.1f}s; expected at least 45s")

    count = len(sources) if animated else min(len(sources), 5)
    sources = sources[:count]
    transition = min(0.35, max(0.18, (total / count) / 14)) if count > 1 else 0.0
    scene = max((total + (count - 1) * transition) / count, 1.0)
    transitions = ["fade", "wipeleft", "slideright", "wiperight", "fade"]
    inputs: list[str] = []
    filters: list[str] = []
    for i, image in enumerate(sources):
        inputs += ["-loop", "1", "-t", f"{scene + transition:.3f}", "-i", str(image)]
        if animated:
            filters.append(
                f"[{i}:v]scale=1120:1992:force_original_aspect_ratio=increase,crop=1120:1992," 
                f"zoompan=z='1.0+0.025*on/({scene*25:.1f})':" 
                f"x='40*on/({scene*25:.1f})':y='22*on/({scene*25:.1f})':" 
                f"d=1:s=1080x1920:fps=25,setsar=1,format=yuv420p[v{i}]"
            )
        else:
            filters.append(f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p[v{i}]")
    current = "v0"
    offset = scene - transition
    for i in range(1, count):
        out = f"xf{i}"
        name = transitions[(i - 1) % len(transitions)]
        filters.append(f"[{current}][v{i}]xfade=transition={name}:duration={transition:.3f}:offset={max(offset, 0):.3f}[{out}]")
        current = out
        offset += scene - transition
    filters.append(f"[{current}]drawbox=x=38:y=38:w=1004:h=1844:color=black@0.10:t=3[finished]")
    current = "finished"
    audio_index = count
    inputs += ["-i", str(audio)]

    if logo:
        try:
            transparent_logo = _prepare_logo(logo, output.parent)
        except Exception:
            transparent_logo = logo
        inputs += ["-i", str(transparent_logo)]
        filters.append(f"[{audio_index+1}:v]format=rgba,scale=260:-1[lg]")
        filters.append(f"[{current}][lg]overlay=40:40:format=auto[branded]")
        current = "branded"
    if captions:
        ass = _srt_to_ass(captions, output.parent)
        cap = ass.as_posix().replace("\\", "/").replace(":", "\\:")
        filters.append(f"[{current}]subtitles='{cap}'[final]")
        current = "final"

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", f"[{current}]", "-map", f"{audio_index}:a:0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", f"{total:.3f}", str(output)]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output


def validate_mp4(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("MP4 missing or empty")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration", "-of", "json", str(path)], check=True, text=True, capture_output=True)
    streams = json.loads(probe.stdout).get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise ValueError("MP4 must contain video and audio streams")
    if video.get("width") != 1080 or video.get("height") != 1920:
        raise ValueError("MP4 must be 1080x1920 (9:16)")
    vd = float(video.get("duration") or 0)
    ad = float(audio.get("duration") or 0)
    if vd + 0.25 < ad:
        raise ValueError(f"Video ends before audio: video={vd:.2f}s audio={ad:.2f}s")
    if vd < 45:
        raise ValueError(f"MP4 duration too short: {vd:.1f}s")
    return {"width": video["width"], "height": video["height"], "video": True, "audio": True, "duration": vd}
