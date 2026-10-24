"""Generate a phone-friendly, sentence-at-a-time Arabic subtitle overlay.

Never truncate its text; wrap the full sentence into the adaptive caption box.

Input JSON may be a list of {text,start,end} objects, or an object with a
'segments' list. Times are seconds. Rendering is performed with FFmpeg and
Pillow using Arial Bold when installed, falling back to DejaVu Sans Bold.
This utility intentionally requires timed segments from the narration/TTS stage;
it will not guess timing from text.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/arialbd.ttf",
        "/usr/share/fonts/truetype/microsoft/Arial_Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for item in candidates:
        if Path(item).exists():
            return ImageFont.truetype(item, size=size)
    return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_sentence_overlay(width: int, height: int, sentence: str, output: Path) -> None:
    """Render one adaptive caption box that contains the entire spoken sentence."""
    scale = width / 1080
    margin_x = int(64 * scale)
    padding_x = int(28 * scale)
    padding_y = int(18 * scale)
    box_width = width - 2 * margin_x
    max_box_height = int(height * 0.32)
    line_gap = max(3, int(6 * scale))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Reduce the font only as much as necessary so every word remains inside the box.
    chosen = None
    for font_size in range(max(18, int(42 * scale)), max(17, int(21 * scale)) - 1, -1):
        font = _font(font_size)
        lines = _wrap(draw, sentence, font, box_width - 2 * padding_x)
        heights = [draw.textbbox((0, 0), line, font=font, direction="rtl", language="ar")[3]
                   for line in lines]
        total_h = sum(heights) + max(0, len(lines) - 1) * line_gap
        needed_h = total_h + 2 * padding_y
        if needed_h <= max_box_height:
            chosen = (font, lines, heights, total_h, min(max_box_height, max(int(height * 0.12), needed_h)))
            break
    if chosen is None:
        # Last-resort small font still wraps the full sentence; never truncate its text.
        font = _font(max(16, int(18 * scale)))
        lines = _wrap(draw, sentence, font, box_width - 2 * padding_x)
        heights = [draw.textbbox((0, 0), line, font=font, direction="rtl", language="ar")[3]
                   for line in lines]
        total_h = sum(heights) + max(0, len(lines) - 1) * line_gap
        box_h = min(height - int(height * 0.06), total_h + 2 * padding_y)
        chosen = (font, lines, heights, total_h, box_h)

    font, lines, heights, total_h, box_height = chosen
    y_top = max(int(height * 0.05), min(int(height * 0.68), height - box_height - int(height * 0.05)))
    radius = int(24 * scale)
    draw.rounded_rectangle(
        (margin_x, y_top, width - margin_x, y_top + box_height),
        radius=radius,
        fill=(255, 255, 255, 242),
        outline=(27, 143, 194, 255),
        width=max(2, int(4 * scale)),
    )
    y = y_top + max(padding_y, (box_height - total_h) // 2)
    for line, line_h in zip(lines, heights):
        draw.text((width // 2, y), line, font=font, fill=(10, 38, 61, 255),
                  anchor="ma", direction="rtl", language="ar")
        y += line_h + line_gap
    image.save(output)


def burn_sentence_subtitles(video_path: str, segments_json: str, output_path: str) -> str:
    video = Path(video_path)
    data = json.loads(Path(segments_json).read_text(encoding="utf-8"))
    segments = data.get("segments", data) if isinstance(data, dict) else data
    if not isinstance(segments, list) or not segments:
        raise ValueError("Subtitle timing JSON must contain a non-empty segments list.")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "json", str(video)], check=True, capture_output=True, text=True
    )
    stream = json.loads(probe.stdout)["streams"][0]
    width, height = int(stream["width"]), int(stream["height"])
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        inputs = []
        graph_parts = ["[0:v]format=rgba[vbase]"]
        previous = "vbase"
        for index, segment in enumerate(segments):
            text = str(segment.get("text", "")).strip()
            start, end = float(segment["start"]), float(segment["end"])
            if not text or start < 0 or end <= start:
                raise ValueError(f"Invalid subtitle segment at index {index}")
            png = tmpdir / f"subtitle-{index:04d}.png"
            render_sentence_overlay(width, height, text, png)
            # Keep each subtitle image available throughout the base video; PTS
            # offsets it to the requested spoken interval, and enable gates display.
            inputs += ["-loop", "1", "-i", str(png)]
            next_label = f"v{index}"
            image_label = f"s{index}"
            graph_parts.append(
                f"[{index+1}:v]format=rgba,setpts=PTS-STARTPTS+{start}/TB[{image_label}]"
            )
            graph_parts.append(
                f"[{previous}][{image_label}]overlay=0:0:"
                f"enable='between(t,{start:.3f},{end:.3f})'[{next_label}]"
            )
            previous = next_label
        graph = ";".join(graph_parts)
        cmd = [
            "ffmpeg", "-y", "-i", str(video), *inputs,
            "-filter_complex", graph,
            "-map", f"[{previous}]", "-map", "0:a?",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=900)

    if not Path(output_path).is_file() or Path(output_path).stat().st_size < 100_000:
        raise RuntimeError("Subtitle renderer did not produce a valid output video.")
    return str(output_path)
