from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from google import genai
from config import load_config
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row
from telegram_bot import send_video
from free_media import cached_fallback_assets, fetch_openverse_images, fetch_wikimedia_images, generate_legal_cards

MPT_REPO = "https://github.com/harry0703/MoneyPrinterTurbo.git"
OUTPUT_ROOT = Path("generated/reels")


def choose_row(rows: list[dict[str, str]]) -> tuple[int, dict[str, str]] | None:
    candidates = []
    for number, row in enumerate(rows, start=2):
        if str(row.get("الحالة", "")).strip().upper() != "PUBLISHED":
            continue
        if str(row.get("Reel Status", "")).strip().upper() in {"GENERATING", "REVIEW", "APPROVED", "PUBLISHED"}:
            continue
        if str(row.get("المحتوى", "")).strip():
            candidates.append((number, row))
    return candidates[-1] if candidates else None


def make_brief(api_key: str, model: str, topic: str, post: str) -> dict[str, Any]:
    client = genai.Client(api_key=api_key)
    prompt = (
        "Create one Arabic legal short-video package for an Egyptian lawyer brand. "
        "Use ONLY the supplied reviewed post and topic. Never invent legal facts. "
        "Natural professional Egyptian Arabic, spoken rhythm, no emojis, no sales pitch. "
        "Strong concrete hook, one practical legal point, useful ending, 45-70 seconds. "
        "Return JSON only with script, video_terms, facebook_caption, linkedin_caption, emotion_map. "
        "video_terms must be English stock-footage searches in chronological order. "
        "emotion_map must contain one item per meaningful sentence with sentence_index and delivery_emotion. "
        "Choose delivery emotions that fit the legal subject and sentence function, such as calm_authority, warning, empathy, urgency, reassurance, clarification, or strong_cta. "
        "The voice must sound like a confident Egyptian male lawyer in his late 30s: natural Egyptian Arabic, clear diction, measured pace, never a newsreader or generic MSA narrator. "
        "Use punctuation, sentence length, pauses, and wording to make the intended emotion audible without inventing legal facts.\n\n"
        "TOPIC:\n" + topic + "\n\nREVIEWED POST:\n" + post
    )
    if os.getenv("REEL_SKIP_GEMINI", "").strip().lower() in {"1", "true", "yes", "on"}:
        print("REEL_SKIP_GEMINI=true; using deterministic Reel brief.")
        return deterministic_brief(topic, post)
    primary = (model or "gemini-3.6-flash").strip()
    fallback = (os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash") or "").strip()
    models = [primary] + ([fallback] if fallback and fallback != primary else [])
    last_error = None
    response = None
    for selected_model in models:
        try:
            response = client.models.generate_content(
                model=selected_model,
                contents=prompt,
                config={"response_mime_type": "application/json", "max_output_tokens": 5000},
            )
            break
        except Exception as exc:
            last_error = exc
            print(f"Reel Gemini model failed: {selected_model}: {exc}")
    if response is None:
        print(f"Gemini unavailable for Reel; using deterministic fallback: {last_error}")
        return deterministic_brief(topic, post)
    data = json.loads((response.text or "").strip())
    script = str(data.get("script", "")).strip()
    terms = data.get("video_terms") if isinstance(data.get("video_terms"), list) else []
    if len(script) < 350 or len(terms) < 4:
        raise RuntimeError("Reel package is incomplete.")
    return {
        "script": script,
        "video_terms": [str(x).strip() for x in terms[:8] if str(x).strip()],
        "facebook_caption": str(data.get("facebook_caption", "")).strip(),
        "linkedin_caption": str(data.get("linkedin_caption", "")).strip(),
        "emotion_map": data.get("emotion_map") if isinstance(data.get("emotion_map"), list) else [],
    }




def deterministic_brief(topic: str, post: str) -> dict[str, Any]:
    text = " ".join(str(post or "").split())
    parts = [p.strip() for p in text.replace("؟", "؟|").replace(".", ".|").split("|") if len(p.strip()) > 35]
    selected = parts[:6]
    body = " ".join(selected)
    if len(body) < 350:
        body = text[:1800]
    script = (
        f"خليني أوضح لك نقطة مهمة جدًا في موضوع {topic}. "
        f"{body} "
        "والأهم قبل ما تاخد أي خطوة إنك تراجع التفاصيل والمستندات المرتبطة بحالتك، لأن التطبيق القانوني بيختلف حسب الوقائع. "
        "لو الموضوع يخصك فعلًا، راجع النص القانوني والمستندات مع محاميك قبل اتخاذ قرار نهائي."
    )
    sentences = [x.strip() for x in script.replace("؟", "؟|").replace(".", ".|").split("|") if x.strip()]
    emotions = []
    for i, sentence in enumerate(sentences, start=1):
        emotion = "strong_cta" if i == len(sentences) else "calm_authority"
        if any(k in sentence for k in ("مهم", "قبل ما", "يختلف")):
            emotion = "warning"
        emotions.append({"sentence_index": i, "delivery_emotion": emotion})
    return {
        "script": script,
        "video_terms": [
            "Egyptian lawyer legal consultation",
            "legal documents paperwork",
            "contract signing close up",
            "law office discussion",
            "court legal files",
            "business legal meeting",
        ],
        "facebook_caption": f"معلومة قانونية مهمة عن {topic}. راجع التفاصيل قبل ما تاخد أي خطوة.",
        "linkedin_caption": f"Legal practical note: {topic}. Review the facts and documents before making a decision.",
        "emotion_map": emotions,
        "generation_mode": "deterministic_fallback",
    }



def build_local_tts_reel(video_path: Path, scene_paths: list[Path], script: str, work_dir: Path) -> Path:
    """Robust local Motion Graphics fallback: Egyptian TTS + animated legal visuals."""
    work_dir.mkdir(parents=True, exist_ok=True)
    audio = work_dir / "voice.mp3"
    subprocess.run([
        "python", "-m", "edge_tts", "--voice", "ar-EG-ShakirNeural",
        "--rate=-4%", "--text", script, "--write-media", str(audio),
    ], check=True, timeout=180)

    # Build six composed visual scenes. External photos are preferred; generated
    # legal cards remain valid inputs. Each scene is then animated with zoom/pan,
    # fades and a progress bar so the fallback is a real motion-graphics reel,
    # not a slideshow of static frames.
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    images = [p for p in scene_paths if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}][:6]
    if not images:
        raise RuntimeError("No image scenes available for Motion Graphics fallback.")

    font_candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    font_path = next((p for p in font_candidates if Path(p).exists()), None)
    title_font = ImageFont.truetype(font_path, 72) if font_path else ImageFont.load_default()
    body_font = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()
    small_font = ImageFont.truetype(font_path, 34) if font_path else ImageFont.load_default()

    sentences = [s.strip() for s in script.replace("؟", "؟|").replace(".", ".|").split("|") if s.strip()]
    while len(sentences) < len(images):
        sentences.append(sentences[-1] if sentences else "معلومة قانونية مهمة")
    sentences = sentences[:len(images)]

    frames = []
    labels = ["HOOK", "النقطة القانونية", "إجراء عملي", "تنبيه", "راجع حالتك", "CTA"]
    for i, (src, sentence) in enumerate(zip(images, sentences)):
        try:
            base = Image.open(src).convert("RGB")
        except Exception:
            continue
        base = ImageOps.fit(base, (1080, 1920), method=Image.Resampling.LANCZOS)
        canvas = base.convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (8, 12, 20, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle((0, 0, 1080, 1920), fill=(8, 12, 20, 85))
        od.rectangle((45, 75, 1035, 270), fill=(8, 12, 20, 185))
        od.rounded_rectangle((45, 75, 410, 155), radius=22, fill=(235, 235, 235, 225))
        od.text((225, 115), labels[i % len(labels)], font=small_font, anchor="mm", fill=(10, 15, 22, 255))
        od.text((540, 210), "خيرات للمحتوى القانوني", font=small_font, anchor="mm", fill=(245, 245, 245, 255))
        # Bottom kinetic-text panel.
        od.rounded_rectangle((55, 1270, 1025, 1780), radius=38, fill=(8, 12, 20, 210))
        od.text((540, 1390), sentence[:180], font=body_font, anchor="ma", fill=(250, 250, 250, 255), align="center")
        od.rectangle((80, 1715, 1000, 1728), fill=(220, 220, 220, 150))
        od.rectangle((80, 1715, 80 + int(920 * ((i + 1) / len(images))), 1728), fill=(250, 250, 250, 235))
        od.text((540, 1840), f"{i+1}/{len(images)}", font=small_font, anchor="mm", fill=(235, 235, 235, 230))
        frames.append(canvas.alpha_composite(overlay).convert("RGB"))

    if not frames:
        raise RuntimeError("Motion Graphics scene rendering produced no frames.")

    frame_paths = []
    for i, frame in enumerate(frames, start=1):
        path = work_dir / f"motion_scene_{i:02d}.jpg"
        frame.save(path, quality=94, optimize=True)
        frame_paths.append(path)

    duration_probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio),
    ], capture_output=True, text=True, check=True, timeout=30)
    audio_duration = max(8.0, float(duration_probe.stdout.strip()))
    per_scene = audio_duration / len(frame_paths)

    scene_videos = []
    for i, frame in enumerate(frame_paths, start=1):
        clip = work_dir / f"motion_clip_{i:02d}.mp4"
        frames_count = max(2, int(per_scene * 30))
        vf = (
            f"zoompan=z='min(zoom+0.0007,1.14)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames_count}:s=1080x1920:fps=30,"
            f"fade=t=in:st=0:d=0.45,fade=t=out:st={max(0.5, per_scene-0.45):.3f}:d=0.45"
        )
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(frame), "-t", f"{per_scene:.3f}",
            "-vf", vf, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            str(clip),
        ], check=True, timeout=180)
        scene_videos.append(clip)

    concat = work_dir / "motion_concat.txt"
    with concat.open("w", encoding="utf-8") as fh:
        for clip in scene_videos:
            fh.write(f"file '{clip.resolve()}'\n")

    video_only = work_dir / "motion_video.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-c", "copy", "-movflags", "+faststart", str(video_only),
    ], check=True, timeout=180)

    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_only), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-t", f"{audio_duration:.3f}",
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(video_path),
    ], check=True, timeout=180)
    return video_path


def main() -> int:
    cfg = load_config()
    service = create_service(cfg["service_account_info"])
    sheet_name = cfg["sheet_range"].split("!", 1)[0]
    ensure_headers(service, cfg["sheet_id"], sheet_name)
    values = get_values(service, cfg["sheet_id"], cfg["sheet_range"])
    selected = choose_row([row_to_dict(row) for row in values[1:]])
    if not selected:
        print("Reel generator: no eligible published content row.")
        return 0

    row_number, row = selected
    topic = str(row.get("الموضوع", "")).strip()
    post = str(row.get("المحتوى", "")).strip()
    output_dir = OUTPUT_ROOT / ("row_" + str(row_number))
    update_row(service, cfg["sheet_id"], sheet_name, row_number, {
        "Reel Status": "GENERATING",
        "Reel Approval": "",
        "Reel Last Error": "",
    })

    try:
        brief = make_brief(cfg["gemini_api_key"], os.getenv("GEMINI_MODEL", "gemini-3.6-flash"), topic, post)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "script.txt").write_text(brief["script"], encoding="utf-8")
        (output_dir / "reel_plan.json").write_text(json.dumps({"topic": topic, **brief}, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "delivery_map.json").write_text(json.dumps(brief.get("emotion_map", []), ensure_ascii=False, indent=2), encoding="utf-8")

        scene_dir = output_dir / "scenes"
        scenes = fetch_openverse_images(brief["video_terms"], scene_dir)
        if len(scenes) < 4:
            needed = max(4, 8 - len(scenes))
            scenes.extend(fetch_wikimedia_images(brief["video_terms"], scene_dir, target=needed))
        if len(scenes) < 4:
            cached = cached_fallback_assets(OUTPUT_ROOT, scene_dir, limit=8)
            scenes.extend(cached)
        if len(scenes) < 4:
            scenes.extend(generate_legal_cards(scene_dir, topic, count=6))
        if len(scenes) < 4:
            raise RuntimeError("لم يتم العثور على عدد كافٍ من المواد المرخّصة مجانًا لهذا الريل.")
        source_file = scene_dir / "sources.json"
        sources = json.loads(source_file.read_text(encoding="utf-8")) if source_file.exists() else []
        attributions = []
        for source in sources:
            if str(source.get("license", "")).lower() == "by":
                title = source.get("title") or "Openverse media"
                creator = source.get("creator") or "unknown creator"
                url = source.get("source_url") or source.get("media_url") or ""
                attributions.append(f"{title} — {creator}" + (f" — {url}" if url else ""))
        if attributions:
            credit_text = "\n\nمصادر المواد البصرية (ترخيص Creative Commons Attribution):\n" + "\n".join(attributions)
            brief["facebook_caption"] = (brief["facebook_caption"] or brief["script"]) + credit_text
            brief["linkedin_caption"] = (brief["linkedin_caption"] or brief["script"]) + credit_text
        (output_dir / "media_sources.json").write_text(
            json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with tempfile.TemporaryDirectory(prefix="khyrat-mpt-") as temp:
            mpt = Path(temp) / "MoneyPrinterTurbo"
            subprocess.run(["git", "clone", "--depth", "1", MPT_REPO, str(mpt)], check=True, timeout=180)
            command = [
                "uv", "run", "--no-project", "--python", "3.11", "python", "docs/skill/mpt_agent.py",
                "--subject", topic,
                "--root", str(mpt),
                "--",
                "--video-script", brief["script"],
                "--video-terms", ", ".join(brief["video_terms"]),
                "--video-source", "local",
                "--video-materials", ",".join(str(p.resolve()) for p in scenes),
                "--video-aspect", "9:16",
                "--video-count", "1",
                "--video-clip-duration", "5",
                "--match-materials-to-script",
                "--voice-name", "ar-EG-ShakirNeural",
            "--voice-rate", "0.96",
                "--subtitle-enabled",
                "--subtitle-position", "bottom",
                "--subtitle-display-mode", "sentence",
                "--subtitle-animation", "none",
                "--font-size", "54",
                "--bgm-type", "random",
                "--bgm-volume", "0.15",
            ]
            env = os.environ.copy()
            result = subprocess.run(command, cwd=mpt, env=env, text=True, capture_output=True, timeout=1800, check=False)
            if result.returncode != 0:
                print("MoneyPrinterTurbo failed; switching to local card + Edge TTS video fallback.")
                build_local_tts_reel(output_dir / "daily-reel.mp4", scenes, brief["script"], output_dir / "fallback_render")
                result = None
            if result is not None:
                video_line = [line for line in result.stdout.splitlines() if line.startswith("VIDEO_FILE=")]
                if not video_line:
                    raise RuntimeError("MoneyPrinterTurbo returned no VIDEO_FILE.")
                video = Path(video_line[-1].split("=", 1)[1].strip())
                output_video = output_dir / "daily-reel.mp4"
                shutil.copy2(video, output_video)

        update_row(service, cfg["sheet_id"], sheet_name, row_number, {
            "Reel Status": "REVIEW",
            "Reel Script": brief["script"],
            "Reel File": str(output_dir / "daily-reel.mp4"),
            "Reel Run ID": os.getenv("GITHUB_RUN_ID", ""),
            "Reel Approval": "",
            "Reel Review": "جاهز للمراجعة اليدوية قبل أي نشر",
            "Reel Last Error": "",
        })
        video_path = output_dir / "daily-reel.mp4"
        try:
            send_video(
                str(video_path),
                caption=f"🎬 Reel للمراجعة — الصف {row_number}\n\nالموضوع: {topic}\n\nالصوت: رجل مصري، نبرة محامٍ واثق، مع خريطة مشاعر حسب الجمل",
                reply_markup={
                    "inline_keyboard": [[
                        {"text": "✅ اعتماد الريل", "callback_data": f"reel_approve:{row_number}"},
                        {"text": "❌ رفض الريل", "callback_data": f"reel_reject:{row_number}"},
                    ]]
                },
            )
        except Exception as notify_exc:
            print(f"Telegram Reel preview unavailable: {notify_exc}")
        print("REEL_READY row=" + str(row_number) + " file=" + str(video_path))
        return 0
    except Exception as exc:
        update_row(service, cfg["sheet_id"], sheet_name, row_number, {
            "Reel Status": "FAILED",
            "Reel Last Error": str(exc)[:1500],
        })
        raise


if __name__ == "__main__":
    raise SystemExit(main())
