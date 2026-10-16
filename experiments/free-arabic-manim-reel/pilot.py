from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import wave
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

ROOT = Path(__file__).resolve().parent
CAIRO = ZoneInfo("Africa/Cairo")
WIDTH, HEIGHT = 1080, 1920
INK = (14, 24, 43)
PANEL = (23, 38, 63)
GOLD = (218, 174, 91)
WHITE = (248, 247, 242)
MUTED = (188, 199, 215)


def _read_secret_json() -> dict:
    raw = (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_CREDENTIALS") or "").strip()
    if not raw:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_CREDENTIALS for read-only Sheet access.")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        import base64
        try:
            value = json.loads(base64.b64decode(raw).decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("Google service-account secret is neither JSON nor base64-encoded JSON.") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Google service-account secret must contain a JSON object.")
    return value


def _sheet_id() -> str:
    value = (os.getenv("GOOGLE_SHEET_ID") or "").strip()
    if value:
        return value
    url = (os.getenv("GOOGLE_SHEET_URL") or "").strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    raise RuntimeError("Missing GOOGLE_SHEET_ID or a valid GOOGLE_SHEET_URL.")


def read_sheet_rows() -> list[dict[str, str]]:
    # Read-only scope: this pilot must never mutate the production content sheet.
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials.from_service_account_info(
        _read_secret_json(),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    sheet_range = (os.getenv("REEL_PILOT_SHEET_RANGE") or os.getenv("GOOGLE_SHEET_RANGE") or "Content!A:BC").strip()
    values = service.spreadsheets().values().get(
        spreadsheetId=_sheet_id(), range=sheet_range, majorDimension="ROWS"
    ).execute().get("values", [])
    if len(values) < 2:
        raise RuntimeError(f"No content rows were returned for {sheet_range}.")
    headers = [str(h).strip() for h in values[0]]
    return [
        {headers[i]: str(row[i]).strip() if i < len(row) else "" for i in range(len(headers))}
        for row in values[1:]
    ]


def _parse_schedule(row: dict[str, str]) -> datetime | None:
    date_text = (row.get("تاريخ النشر") or row.get("Scheduled Date") or row.get("Publish Date") or "").strip()
    time_text = (row.get("ساعة النشر") or row.get("Scheduled Time") or row.get("Publish Time") or "").strip()
    if not date_text:
        return None
    formats = (
        "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y",
        "%d.%m.%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M",
    )
    parsed = None
    for fmt in formats:
        try:
            parsed = datetime.strptime(date_text, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo:
        scheduled = parsed.astimezone(CAIRO)
    else:
        if parsed.hour == 0 and parsed.minute == 0 and time_text:
            parsed_time = None
            for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p"):
                try:
                    parsed_time = datetime.strptime(time_text, fmt).time()
                    break
                except ValueError:
                    continue
            if parsed_time:
                parsed = datetime.combine(parsed.date(), parsed_time)
        scheduled = parsed.replace(tzinfo=CAIRO)
    return scheduled


def choose_next_row(rows: list[dict[str, str]], now: datetime | None = None) -> tuple[dict[str, str], datetime]:
    now = now or datetime.now(CAIRO)
    candidates = []
    for row in rows:
        topic = (row.get("الموضوع") or row.get("Topic") or row.get("Title") or "").strip()
        status = (row.get("الحالة") or row.get("Status") or "").strip().casefold()
        if not topic or status in {"published", "تم النشر", "cancelled", "canceled", "ملغي", "مرفوض"}:
            continue
        scheduled = _parse_schedule(row)
        if scheduled and scheduled >= now:
            candidates.append((scheduled, row))
    if not candidates:
        raise RuntimeError("No future scheduled row with a recognizable date/time and topic was found. Refusing to guess an arbitrary topic.")
    scheduled, row = min(candidates, key=lambda item: item[0])
    return row, scheduled


def _clean_text(value: str) -> str:
    value = re.sub(r"https?://\S+", "", str(value or ""), flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[#*_\[\]{}|]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _sentences(text: str) -> list[str]:
    text = _clean_text(text)
    parts = re.split(r"(?<=[.!؟?])\s+", text)
    return [p.strip(" \n\t-•") for p in parts if len(p.strip()) >= 25]


def build_script(row: dict[str, str], override_topic: str = "", demo_content: str = "") -> dict:
    topic = _clean_text(override_topic or row.get("الموضوع") or row.get("Topic") or row.get("Title") or "")
    if not topic:
        raise RuntimeError("The selected row has no topic.")
    source = _clean_text(demo_content or row.get("المحتوى") or row.get("Content") or row.get("المقال") or row.get("Article") or "")
    sentences = _sentences(source)
    core = sentences[:3]
    if not core:
        core = [
            "ابدأ بتحديد الوقائع والمستندات المرتبطة بالموضوع قبل اتخاذ أي خطوة.",
            "راجع النص القانوني المصري الساري، لأن التفاصيل والمواعيد تختلف حسب الحالة.",
            "احتفظ بنسخ من المستندات، ولا تعتمد على معلومة عامة بدل مراجعة الحالة نفسها.",
        ]
    intro = f"خلينا نفهم بسرعة: {topic}."
    outro = "دي معلومات عامة للتوعية، مش بديل عن مراجعة النص القانوني وتفاصيل حالتك مع محامٍ مختص."
    cta = "احفظ الريل وشارك سؤالك في التعليقات، وتابعنا لمحتوى قانوني عملي."
    slide_texts = [
        (topic, intro),
        ("أول نقطة", core[0]),
        ("خلي بالك", core[1] if len(core) > 1 else "راجع النص القانوني الساري وتأكد من المواعيد والإجراءات الخاصة بحالتك."),
        ("خطوة عملية", core[2] if len(core) > 2 else "رتّب المستندات واحتفظ بنسخ واضحة قبل اتخاذ أي إجراء."),
        ("الخلاصة", outro + " " + cta),
    ]
    slides = [{"title": title, "body": body, "narration": body} for title, body in slide_texts]
    return {
        "topic": topic,
        "source_id": _clean_text(row.get("ID", "")),
        "scheduled_at": row.get("تاريخ النشر", "") + " " + row.get("ساعة النشر", ""),
        "slides": slides,
        "narration": " ".join(slide["narration"] for slide in slides),
        "legal_review_required": True,
        "publishing_enabled": False,
    }


def _font_path(bold: bool = False) -> str:
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("No supported Arabic font found. Install fonts-noto-core.")


def _shape(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


def _wrap_rtl(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), _shape(candidate), font=font)[2] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_slide(path: Path, index: int, title: str, body: str, total: int) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), INK)
    draw = ImageDraw.Draw(image)
    # Subtle geometry, fixed margins, no photographic assets and therefore no image warping.
    draw.rounded_rectangle((52, 54, WIDTH - 52, HEIGHT - 54), radius=38, fill=PANEL, outline=(51, 72, 102), width=3)
    draw.rounded_rectangle((88, 100, WIDTH - 88, 118), radius=8, fill=GOLD)
    small = ImageFont.truetype(_font_path(True), 32)
    heading = ImageFont.truetype(_font_path(True), 64 if index else 58)
    body_font = ImageFont.truetype(_font_path(False), 48)
    footer = ImageFont.truetype(_font_path(False), 28)
    draw.text((WIDTH - 100, 160), _shape(f"محتوى قانوني مصري  •  {index + 1}/{total}"), font=small, fill=GOLD, anchor="ra")
    title_lines = _wrap_rtl(draw, title, heading, WIDTH - 220)
    y = 360
    for line in title_lines[:3]:
        draw.text((WIDTH - 120, y), _shape(line), font=heading, fill=WHITE, anchor="ra", stroke_width=0)
        y += 92
    y += 100
    body_lines = _wrap_rtl(draw, body, body_font, WIDTH - 220)
    for line in body_lines[:9]:
        draw.text((WIDTH - 120, y), _shape(line), font=body_font, fill=MUTED, anchor="ra")
        y += 76
    draw.rounded_rectangle((120, HEIGHT - 270, WIDTH - 120, HEIGHT - 264), radius=3, fill=GOLD)
    draw.text((WIDTH - 120, HEIGHT - 220), _shape("اسأل محمود • للتوعية القانونية"), font=footer, fill=WHITE, anchor="ra")
    image.save(path, quality=95)


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())


def build_voice_and_slides(script: dict, out: Path) -> list[float]:
    from voicetut_tts import VoiceTutTTS

    slides_dir = out / "slides"
    audio_dir = out / "audio"
    slides_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    tts = VoiceTutTTS.from_pretrained("mohammedaly22/VoiceTut-TTS")
    durations = []
    for index, slide in enumerate(script["slides"]):
        image_path = slides_dir / f"slide_{index:02d}.png"
        audio_path = audio_dir / f"voice_{index:02d}.wav"
        render_slide(image_path, index, slide["title"], slide["body"], len(script["slides"]))
        tts.synthesize(slide["narration"], speaker=os.getenv("VOICETUT_SPEAKER", "Mohamed"), output=str(audio_path))
        if not audio_path.exists() or audio_path.stat().st_size < 2048:
            raise RuntimeError(f"TTS did not create a valid WAV for slide {index}.")
        durations.append(_wav_duration(audio_path))
    return durations


def render_manim(out: Path, durations: list[float]) -> Path:
    scene_json = out / "scene.json"
    scene_json.write_text(json.dumps({"durations": durations, "slides": [str(p.resolve()) for p in sorted((out / "slides").glob("slide_*.png"))]}, ensure_ascii=False), encoding="utf-8")
    scene_file = ROOT / "scene.py"
    env = os.environ.copy()
    env["REEL_PILOT_SCENE_JSON"] = str(scene_json.resolve())
    command = [
        sys.executable, "-m", "manim", "-ql", "--disable_caching",
        "--format", "mp4", str(scene_file), "FreeArabicReelScene",
    ]
    subprocess.run(command, check=True, cwd=out, env=env)
    matches = sorted(out.glob("media/videos/scene/480p15/FreeArabicReelScene.mp4"))
    if not matches:
        matches = list(out.rglob("FreeArabicReelScene.mp4"))
    if not matches:
        raise RuntimeError("Manim completed but no scene MP4 was found.")
    return matches[0]


def _concat_audio(out: Path) -> Path:
    list_file = out / "audio_list.txt"
    audios = sorted((out / "audio").glob("voice_*.wav"))
    if not audios:
        raise RuntimeError("No narration WAV files were created.")
    list_file.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in audios), encoding="utf-8")
    combined = out / "narration.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c:a", "pcm_s16le", str(combined)], check=True, capture_output=True)
    return combined


def validate_mp4(path: Path) -> dict:
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name", "-of", "json", str(path)
    ], check=True, capture_output=True, text=True)
    video = json.loads(probe.stdout)["streams"][0]
    audio_probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate", "-of", "json", str(path)
    ], check=True, capture_output=True, text=True)
    if int(video["width"]) != WIDTH or int(video["height"]) != HEIGHT:
        raise RuntimeError(f"Aspect-ratio QA failed: expected {WIDTH}x{HEIGHT}, got {video['width']}x{video['height']}.")
    if not audio_probe.stdout.strip() or not json.loads(audio_probe.stdout).get("streams"):
        raise RuntimeError("Audio QA failed: final MP4 has no audio stream.")
    return {"width": int(video["width"]), "height": int(video["height"]), "video_codec": video.get("codec_name"), "audio_codec": json.loads(audio_probe.stdout)["streams"][0].get("codec_name")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="", help="Optional explicit topic for a non-production smoke test.")
    parser.add_argument("--demo-content", default="", help="Optional content used only with --topic.")
    parser.add_argument("--output-dir", default="out")
    args = parser.parse_args()
    if args.topic and not args.demo_content:
        print("WARNING: explicit topic without demo content will use general legal-safety narration.", file=sys.stderr)
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.topic:
        row = {"الموضوع": args.topic, "المحتوى": args.demo_content, "ID": "DEMO", "تاريخ النشر": "", "ساعة النشر": ""}
    else:
        row, scheduled = choose_next_row(read_sheet_rows())
        print(f"Read-only Sheet selection: topic={row.get('الموضوع', '')!r}, scheduled={scheduled.isoformat()}")
    script = build_script(row, args.topic, args.demo_content)
    (out / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    durations = build_voice_and_slides(script, out)
    scene = render_manim(out, durations)
    narration = _concat_audio(out)
    final_mp4 = out / "free-arabic-legal-reel.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(scene), "-i", str(narration),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-shortest", "-movflags", "+faststart", str(final_mp4),
    ], check=True)
    qa = validate_mp4(final_mp4)
    qa.update({"file": final_mp4.name, "bytes": final_mp4.stat().st_size, "topic": script["topic"], "source_id": script["source_id"], "publishing_enabled": False, "review_required": True})
    (out / "qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(qa, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
