from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from google import genai
from config import load_reel_config
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row
from telegram_bot import send_video
from free_media import cached_fallback_assets, fetch_openverse_images, fetch_wikimedia_images, generate_legal_cards

MPT_REPO = "https://github.com/harry0703/MoneyPrinterTurbo.git"
MPT_REF = "main"
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


def egyptian_spoken_text(text: str) -> str:
    """Normalize legal copy toward natural Egyptian spoken Arabic before TTS."""
    replacements = [
        ("ما يجب عليك فعله", "إنت تعمل إيه"), ("يجب عليك", "لازم"), ("يجب أن", "لازم"),
        ("ينبغي أن", "الأفضل إنك"), ("في حالة", "لو"), ("في حال", "لو"),
        ("هذه", "دي"), ("هذا", "ده"), ("هؤلاء", "دول"), ("ذلك", "ده"), ("تلك", "دي"),
        ("الذي", "اللي"), ("التي", "اللي"), ("الذين", "اللي"), ("حيث إن", "لأن"),
        ("حيث", "لأن"), ("بالتالي", "وعشان كده"), ("لذلك", "وعشان كده"), ("لكن", "بس"),
        ("أيضًا", "كمان"), ("أيضا", "كمان"), ("إذا", "لو"), ("عندئذ", "ساعتها"),
        ("حينئذ", "ساعتها"), ("يتعين", "لازم"), ("يمكنك", "تقدر"), ("يمكن أن", "ممكن"),
        ("وفقًا", "حسب"), ("وفقاً", "حسب"), ("لا سيما", "خصوصًا"), ("من ثم", "وعشان كده"),
        ("فيما يتعلق", "بالنسبة لـ"), ("يرجى", "خليك"),
    ]
    out = " ".join(str(text or "").split())
    for src, dst in replacements: out = out.replace(src, dst)
    out = re.sub(r"\s+", " ", out).strip()
    return out

def topic_visual_terms(topic: str) -> list[str]:
    t = (topic or "").lower()
    groups = [
        (("تحرش", "تحرش جنسي"), ["Egyptian street harassment victim phone evidence","woman documenting harassment on smartphone","security camera footage street evidence","police report desk Egypt legal complaint","lawyer explaining harassment case to client","digital messages evidence smartphone close up"]),
        (("طلاق", "خلع", "نفقة", "حضانة"), ["Egyptian family law consultation divorce documents","divorce papers legal documents close up","Egyptian family lawyer meeting client","child custody legal documents family court","alimony financial documents legal consultation","lawyer explaining family court procedure"]),
        (("إيجار", "طرد", "عقد إيجار"), ["Egypt rental apartment lease contract signing","tenant landlord lease documents close up","rental contract legal dispute lawyer","apartment keys lease agreement close up","Egyptian lawyer reviewing rental contract","eviction legal notice document close up"]),
        (("شيك", "نصب", "احتيال", "خيانة أمانة"), ["bank cheque legal dispute close up","fraud evidence smartphone financial transaction","financial documents lawyer investigation","police complaint financial fraud paperwork","lawyer explaining fraud case documents","court evidence financial dispute"]),
        (("عمل", "فصل", "موظف", "عمال", "مرتب"), ["employee employment contract office close up","worker reviewing employment documents","termination letter legal document close up","salary dispute paperwork lawyer consultation","Egyptian employment lawyer meeting employee","workplace rights legal consultation"]),
    ]
    for keys, terms in groups:
        if any(k in t for k in keys): return terms
    return [f"{topic} legal documents close up", f"{topic} lawyer consultation Egypt", f"{topic} evidence smartphone documents", f"{topic} legal notice paperwork", f"{topic} Egyptian court legal case", f"{topic} lawyer explaining case to client", "legal evidence close up documents", "Egyptian lawyer legal consultation"]

def make_brief(api_key: str, model: str, topic: str, post: str) -> dict[str, Any]:
    client = genai.Client(api_key=api_key)
    prompt = (
        "Create one Arabic legal short-video package for an Egyptian lawyer brand. "
        "Use ONLY the supplied reviewed post and topic. Never invent legal facts. "
        "Natural Egyptian Arabic as actually spoken in Cairo, not Modern Standard Arabic. Write for the mouth: contractions, short phrases, pauses, and direct address. Avoid robotic legal-news phrasing and MSA connectors such as يجب، ينبغي، حيث، لذلك، وبالتالي، يتعين. "
        "Open with a truthful high-tension hook, then 3-5 escalating beats, one concrete practical action, and a strong ending. Target 55-75 seconds and 125-145 Arabic words. No filler or repeated disclaimer. "
        "Return JSON only with script, video_terms, facebook_caption, linkedin_caption, emotion_map. "
        "video_terms must be 8 highly specific English visual searches, one per scene, directly tied to the topic and sentence; never generic courtroom/lawyer images when the sentence is about a different concrete event. "
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
    raw_text = (response.text or "").strip()
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        print(f"Gemini Reel response was not valid JSON; using deterministic fallback: {exc}")
        return deterministic_brief(topic, post)
    script = egyptian_spoken_text(str(data.get("script", "")).strip())
    terms = data.get("video_terms") if isinstance(data.get("video_terms"), list) else []
    if len(terms) < 6: terms = topic_visual_terms(topic)
    if len(script.split()) < 115 or len(terms) < 6:
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
    # Keep a short, spoken core from the reviewed post so free TTS remains
    # within the intended 55-75 second Reel window.
    post_sentences = [s.strip() for s in re.split(r"(?<=[؟!.])\s+", text) if s.strip()]
    selected_words: list[str] = []
    for sentence in post_sentences:
        words = sentence.split()
        if len(selected_words) + len(words) > 30:
            break
        selected_words.extend(words)
    core = " ".join(selected_words)
    script = (
        f"بص، لو الموضوع ده يخصك، ما تاخدش خطوة وإنت مستعجل. "
        f"في موضوع {topic}، التفاصيل الصغيرة ممكن تغيّر الموقف كله. {core} "
        "قبل ما تبعت رسالة، تمضي ورقة، أو تدخل في مواجهة، اجمع الرسائل والعقود والإيصالات والصور وأي دليل على اللي حصل. "
        "ومتعتمدش على جزء واحد من القصة؛ التسلسل والمستندات بيفرقوا جدًا. "
        "والخطوة الصح مش إنك تعمل أي إجراء بسرعة؛ اختار الإجراء المناسب للوقائع اللي عندك. "
        "لو الموضوع يخصك، راجع المستندات والتفاصيل مع محاميك قبل ما تاخد قرار."
    )
    script = egyptian_spoken_text(script)
    if len(script.split()) < 115:
        script += " وخلي بالك: نفس الموضوع ممكن يختلف من واقعة للتانية حسب المستندات والتفاصيل وإيه اللي تقدر تثبته."
    sentences = [x.strip() for x in re.split(r"(?<=[؟!.])\s+", script) if x.strip()]
    emotions = []
    for i, sentence in enumerate(sentences, start=1):
        emotion = "strong_hook" if i == 1 else ("strong_cta" if i == len(sentences) else "calm_authority")
        if any(k in sentence for k in ("ما تاخدش", "قبل ما", "خلي بالك", "مت")): emotion = "warning"
        elif any(k in sentence for k in ("اجمع", "الرسائل", "العقود", "الإيصالات")): emotion = "urgency"
        emotions.append({"sentence_index": i, "delivery_emotion": emotion})
    return {
        "script": script,
        "video_terms": topic_visual_terms(topic),
        "facebook_caption": f"معلومة قانونية عملية عن {topic}. التفاصيل والمستندات بتفرق.",
        "linkedin_caption": f"معلومة قانونية عملية عن {topic}: راجع الوقائع والمستندات قبل اتخاذ أي خطوة.",
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
        frames.append(Image.alpha_composite(canvas, overlay).convert("RGB"))

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
    cfg = load_reel_config()
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
        # Never recycle unrelated cached imagery into a new legal Reel.
        # Fill missing slots with original topic-labeled graphics instead.
        if len(scenes) < 8:
            scenes.extend(generate_legal_cards(scene_dir, topic, count=8 - len(scenes)))
        if len(scenes) < 8:
            raise RuntimeError("لم يتم توفير 8 مشاهد مرتبطة بالموضوع لهذا الريل.")

        # Normalize externally sourced WebP assets to JPEG because the current
        # MPT local-material validator accepts JPG/PNG but not WebP.
        normalized_scenes: list[Path] = []
        from PIL import Image
        for scene in scenes:
            if scene.suffix.lower() == ".webp":
                normalized = scene.with_suffix(".jpg")
                Image.open(scene).convert("RGB").save(normalized, quality=94, optimize=True)
                normalized_scenes.append(normalized)
            else:
                normalized_scenes.append(scene)
        scenes = normalized_scenes
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
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", MPT_REF, MPT_REPO, str(mpt)],
                check=True,
                timeout=180,
            )

            # Use the native MPT CLI directly. The agent wrapper performs an
            # unnecessary LLM-provider preflight even when a complete script and
            # local materials are supplied; direct CLI keeps this Reel path
            # genuinely keyless after our own Gemini/deterministic brief stage.
            task_id = __import__("uuid").uuid4()
            command = [
                "uv", "run", "python", "cli.py",
                "--video-subject", topic,
                "--video-script", brief["script"],
                "--video-terms", ", ".join(brief["video_terms"]),
                "--video-source", "local",
                "--video-materials", ",".join(str(p.resolve()) for p in scenes),
                "--video-aspect", "9:16",
                "--video-count", "1",
                "--video-clip-duration", "9",
                "--video-clip-speed", "1.0",
                "--video-concat-mode", "sequential",
                "--video-transition-mode", "shuffle",
                "--match-materials-to-script",
                "--voice-name", "ar-EG-ShakirNeural",
                "--voice-rate", "0.96",
                "--subtitle-enabled",
                "--subtitle-position", "bottom",
                "--subtitle-display-mode", "word_by_word",
                "--subtitle-animation", "pop_spring",
                "--font-size", "54",
                "--bgm-type", "none",
                "--bgm-volume", "0",
                "--stop-at", "video",
                "--task-id", str(task_id),
            ]
            env = os.environ.copy()
            result = subprocess.run(
                ["uv", "sync", "--frozen"],
                cwd=mpt,
                env=env,
                text=True,
                capture_output=True,
                timeout=900,
                check=False,
            )
            if result.returncode != 0:
                print("MoneyPrinterTurbo dependency sync failed; switching to local Edge TTS renderer.")
                print((result.stdout or "")[-5000:])
                print((result.stderr or "")[-5000:])
                build_local_tts_reel(
                    output_dir / "daily-reel.mp4",
                    scenes,
                    egyptian_spoken_text(brief["script"]),
                    output_dir / "fallback_render",
                )
            else:
                result = subprocess.run(
                    command,
                    cwd=mpt,
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=1800,
                    check=False,
                )
                if result.returncode != 0:
                    print("MoneyPrinterTurbo native CLI failed; switching to local Edge TTS renderer.")
                    print((result.stdout or "")[-5000:])
                    print((result.stderr or "")[-5000:])
                    build_local_tts_reel(
                        output_dir / "daily-reel.mp4",
                        scenes,
                        egyptian_spoken_text(brief["script"]),
                        output_dir / "fallback_render",
                    )
                else:
                    task_videos = sorted(
                        (mpt / "storage" / "tasks" / str(task_id)).glob("final-*.mp4")
                    )
                    if not task_videos:
                        raise RuntimeError(
                            "MoneyPrinterTurbo completed without producing final-*.mp4."
                        )
                    output_video = output_dir / "daily-reel.mp4"
                    shutil.copy2(task_videos[-1], output_video)

                    probe = subprocess.run(
                        [
                            "ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(output_video),
                        ],
                        capture_output=True, text=True, check=True, timeout=30,
                    )
                    duration = float(probe.stdout.strip() or "0")
                    streams = subprocess.run(
                        [
                            "ffprobe", "-v", "error", "-select_streams", "a:0",
                            "-show_entries", "stream=codec_name",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(output_video),
                        ],
                        capture_output=True, text=True, check=True, timeout=30,
                    )
                    if duration < 50 or duration > 80 or not streams.stdout.strip():
                        raise RuntimeError(
                            f"Invalid Reel render: duration={duration:.1f}s "
                            f"audio={'yes' if streams.stdout.strip() else 'no'}"
                        )

        video_path = output_dir / "daily-reel.mp4"
        # Telegram delivery is part of the review contract: do not mark a Reel
        # REVIEW unless the actual MP4 was successfully delivered for approval.
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

        update_row(service, cfg["sheet_id"], sheet_name, row_number, {
            "Reel Status": "REVIEW",
            "Reel Script": brief["script"],
            "Reel File": str(output_dir / "daily-reel.mp4"),
            "Reel Run ID": os.getenv("GITHUB_RUN_ID", ""),
            "Reel Approval": "",
            "Reel Review": "جاهز للمراجعة اليدوية قبل أي نشر",
            "Reel Last Error": "",
        })
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

# Production render test: verify the complete Reel path before review delivery.
