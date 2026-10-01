from __future__ import annotations

import base64
import json
import urllib.request
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
MPT_REF = "v1.3.7"
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
    """Prepare natural, spoken Egyptian Arabic without synthesis-hostile symbols."""
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
    for src, dst in replacements:
        out = out.replace(src, dst)
    # TTS-safe: no hashtags, URLs, brackets, slashes, percent signs, Latin handles,
    # or stray markup that a speech model might read literally.
    out = re.sub(r"https?://\\S+", "", out, flags=re.I)
    out = re.sub(r"[@#%*_{}\[\]<>|\\/]+", " ", out)
    out = re.sub(r"\b(?:API|SEO|GEO|CTA|FAQ|URL)\b", "", out, flags=re.I)
    out = re.sub(r"\s+", " ", out).strip(" .،؛:|-")
    return out


def prepare_tts_script(text: str) -> str:
    """Final spoken-script gate: plain Arabic text, punctuation only, no markup."""
    out = egyptian_spoken_text(text)
    # Keep punctuation that helps Gemini TTS pace the narration, but remove symbols
    # which are commonly interpreted as literal words or metadata.
    out = out.replace("(", " ").replace(")", " ").replace("…", "...").replace("؛", "،")
    out = re.sub(r"\.{2,}", "...", out)
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"\d+", " ", out)
    if not out:
        raise RuntimeError("TTS script is empty after sanitization.")
    try:
        from text2tashkeel import Diacritizer
        out = Diacritizer("rawi-ensemble").diacritize(out)
    except Exception as exc:
        raise RuntimeError(f"Arabic diacritization failed: {exc}") from exc
    return out


def generate_gemini_tts_audio(api_key: str, script: str, emotion_map: list[dict[str, Any]], output_path: Path) -> Path:
    """Generate the Reel narration with Gemini 3.8 Flash TTS, not Edge TTS."""
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for Reel narration.")
    clean = prepare_tts_script(script)
    # Sentence-level metadata controls delivery without being spoken. The model
    # supports Egyptian Arabic and style instructions in speech_metadata.
    sentences = [s.strip() for s in re.split(r"(?<=[؟!.])\s+", clean) if s.strip()]
    content = []
    for idx, sentence in enumerate(sentences, start=1):
        emotion = "confident, natural Egyptian Arabic, clear lawyer-like diction"
        for item in emotion_map or []:
            if int(item.get("sentence_index", 0) or 0) == idx:
                emotion = str(item.get("delivery_emotion") or emotion).replace("_", " ")
                break
        content.append({
            "type": "text",
            "text": sentence,
            "annotations": [{
                "type": "speech_metadata",
                "style": (
                    "Egyptian Arabic, mature male legal presenter, natural Cairo delivery; "
                    + emotion +
                    "; conversational, human, not a newsreader, with natural pauses"
                ),
            }],
        })
    payload = {
        "model": os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts"),
        "input": [{"type": "user_input", "content": content}],
        "response_format": {"type": "audio"},
        "generation_config": {
            "speech_config": [{"voice": os.getenv("GEMINI_TTS_VOICE", "Orus")}]
        },
    }
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Gemini TTS request failed: {exc}") from exc
    encoded = ((data.get("interaction") or {}).get("output_audio") or {}).get("data")
    if not encoded:
        raise RuntimeError(f"Gemini TTS returned no audio: {str(data)[:1000]}")
    try:
        output_path.write_bytes(base64.b64decode(encoded))
    except Exception as exc:
        raise RuntimeError(f"Invalid Gemini TTS audio payload: {exc}") from exc
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)], capture_output=True, text=True, check=True, timeout=30)
    duration = float(probe.stdout.strip() or "0")
    if duration < 45 or duration > 80:
        raise RuntimeError(f"Gemini TTS duration outside Reel target: {duration:.1f}s")
    return output_path


def add_motion_graphics_layer(input_video: Path, output_video: Path) -> Path:
    """Add energetic, non-text kinetic design without Arabic subtitle rendering."""
    vf = (
        "drawbox=x=28:y=28:w=1024:h=1864:color=white@0.13:t=4,"
        "drawbox=x='mod(t*190,1250)-160':y='120+150*sin(t*1.05)':w=10:h=620:color=white@0.20:t=fill,"
        "drawbox=x='930+70*sin(t*0.82)':y='mod(t*260,2150)-220':w=16:h=360:color=white@0.15:t=fill,"
        "drawbox=x='120+300*sin(t*0.64)':y='1740+35*sin(t*1.8)':w=300:h=7:color=white@0.34:t=fill,"
        "drawbox=x='40+90*sin(t*0.55)':y='420+110*cos(t*0.7)':w=5:h=980:color=white@0.10:t=fill,"
        "vignette=PI/5"
    )
    subprocess.run(
        ["ffmpeg","-y","-i",str(input_video),"-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","20","-c:a","copy","-movflags","+faststart",str(output_video)],
        check=True, timeout=900,
    )
    return output_video


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


def add_motion_graphics(video_path: Path, topic: str, work_dir: Path) -> Path:
    """Add text-free kinetic graphics over the footage."""
    from PIL import Image, ImageDraw
    work_dir.mkdir(parents=True, exist_ok=True)

    orb = Image.new("RGBA", (360, 360), (0, 0, 0, 0))
    d = ImageDraw.Draw(orb)
    d.ellipse((45, 45, 315, 315), outline=(255, 255, 255, 170), width=5)
    d.ellipse((95, 95, 265, 265), outline=(255, 255, 255, 95), width=3)
    d.ellipse((165, 25, 195, 55), fill=(255, 255, 255, 210))
    d.ellipse((300, 175, 330, 205), fill=(255, 255, 255, 180))
    orb_path = work_dir / "mg_orb.png"
    orb.save(orb_path)

    card = Image.new("RGBA", (420, 560), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((35, 25, 385, 535), radius=34, fill=(18, 24, 34, 235), outline=(255, 255, 255, 130), width=4)
    d.rounded_rectangle((75, 85, 345, 125), radius=15, fill=(255, 255, 255, 35))
    for y, w in ((175, 210), (230, 260), (285, 185), (340, 235)):
        d.rounded_rectangle((75, y, 75 + w, y + 18), radius=9, fill=(255, 255, 255, 105))
    d.ellipse((250, 390, 350, 490), outline=(255, 255, 255, 180), width=6)
    d.line((270, 440, 295, 465), fill=(255, 255, 255, 220), width=8)
    d.line((295, 465, 330, 420), fill=(255, 255, 255, 220), width=8)
    card_path = work_dir / "mg_evidence_card.png"
    card.save(card_path)

    phone = Image.new("RGBA", (330, 620), (0, 0, 0, 0))
    d = ImageDraw.Draw(phone)
    d.rounded_rectangle((25, 15, 305, 605), radius=42, fill=(12, 18, 28, 245), outline=(255, 255, 255, 160), width=5)
    d.rounded_rectangle((55, 85, 275, 530), radius=26, fill=(255, 255, 255, 20))
    d.rounded_rectangle((75, 145, 235, 205), radius=28, fill=(255, 255, 255, 125))
    d.rounded_rectangle((95, 235, 255, 295), radius=28, fill=(255, 255, 255, 75))
    d.rounded_rectangle((75, 325, 215, 385), radius=28, fill=(255, 255, 255, 125))
    d.ellipse((140, 545, 190, 595), fill=(255, 255, 255, 180))
    phone_path = work_dir / "mg_phone.png"
    phone.save(phone_path)

    styled = work_dir / "daily-reel-motion.mp4"
    filter_complex = (
        "[1:v]format=rgba[orb];[2:v]format=rgba[card];[3:v]format=rgba[phone];"
        "[0:v][orb]overlay=x='55+55*sin(0.8*t)':y='230+80*cos(0.55*t)':eval=frame[v1];"
        "[v1][card]overlay=x='720-80*sin(0.45*t)':y='780+65*cos(0.65*t)':eval=frame:enable='gte(t,3)'[v2];"
        "[v2][phone]overlay=x='-25+55*sin(0.38*t)':y='980+45*cos(0.72*t)':eval=frame:enable='gte(t,8)'[v3]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-loop", "1", "-i", str(orb_path),
        "-loop", "1", "-i", str(card_path),
        "-loop", "1", "-i", str(phone_path),
        "-filter_complex", filter_complex,
        "-map", "[v3]", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "copy", "-movflags", "+faststart", str(styled),
    ], check=True, timeout=900)
    shutil.copy2(styled, video_path)
    return video_path

def make_brief(api_key: str, model: str, topic: str, post: str) -> dict[str, Any]:
    client = genai.Client(api_key=api_key)
    prompt = (
        "Create one Arabic legal short-video package for an Egyptian lawyer brand. "
        "Use ONLY the supplied reviewed post and topic. Never invent legal facts. "
        "Natural Egyptian Arabic as actually spoken in Cairo, not Modern Standard Arabic. Return the script fully vowel-marked with tashkeel where useful for pronunciation. Write for the mouth: contractions, short phrases, pauses, and direct address. Fully vowel-mark the spoken script with Arabic diacritics wherever useful for pronunciation. Avoid robotic legal-news phrasing and MSA connectors such as يجب، ينبغي، حيث، لذلك، وبالتالي، يتعين. Never use hashtags, @, %, slashes, URLs, brackets, markdown, emoji, Latin abbreviations, or unexplained numbers in the spoken script; spell numbers as Arabic words. "
        "Open with a truthful high-tension hook, then 3-5 escalating beats, one concrete practical action, and a strong ending. Target 55-75 seconds and 125-145 Arabic words. No filler or repeated disclaimer. "
        "Return JSON only with script, video_terms, facebook_caption, linkedin_caption, emotion_map. "
        "video_terms must be 8 highly specific English visual searches, one per scene, directly tied to the topic and sentence; never generic courtroom/lawyer images when the sentence is about a different concrete event. "
        "emotion_map must contain one item per meaningful sentence with sentence_index and delivery_emotion. "
        "Choose delivery emotions that fit the legal subject and sentence function, such as calm_authority, warning, empathy, urgency, reassurance, clarification, or strong_cta. "
        "The voice must sound like a confident Egyptian male lawyer in his late 30s: natural Egyptian Arabic, clear diction, measured pace, never a newsreader or generic MSA narrator. "
        "Use Arabic punctuation only. Never use hashtags, URLs, markdown, symbols, Latin letters, digits, brackets, slashes, or notation that could be spoken incorrectly. Spell numbers out as Arabic words. Use punctuation, sentence length, pauses, and wording to make the intended emotion audible without inventing legal facts.\n\n"
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
    script = prepare_tts_script(str(data.get("script", "")).strip())
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
    # Keep a short, spoken core from the reviewed post. This fallback is used only
    # when the script LLM is unavailable; narration itself still requires Gemini TTS.
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
    script = prepare_tts_script(script)
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
        brief["script"] = prepare_tts_script(brief["script"])
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

        tts_audio = output_dir / "voice-gemini.wav"
        generate_gemini_tts_audio(cfg["gemini_api_key"], brief["script"], brief.get("emotion_map", []), tts_audio)

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
                "--custom-audio-file", str(tts_audio.resolve()),
                "--no-subtitle-enabled",
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
                raise RuntimeError("MoneyPrinterTurbo dependency sync failed: " + (result.stderr or result.stdout)[-5000:])
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
                    raise RuntimeError("MoneyPrinterTurbo native CLI failed: " + (result.stderr or result.stdout)[-5000:])
                else:
                    task_videos = sorted(
                        (mpt / "storage" / "tasks" / str(task_id)).glob("final-*.mp4")
                    )
                    if not task_videos:
                        raise RuntimeError(
                            "MoneyPrinterTurbo completed without producing final-*.mp4."
                        )
                    raw_video = output_dir / "mpt-base.mp4"
                    shutil.copy2(task_videos[-1], raw_video)
                    output_video = output_dir / "daily-reel.mp4"
                    add_motion_graphics_layer(raw_video, output_video)
                    raw_video.unlink(missing_ok=True)


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


# Reel production verification: Gemini TTS + text-free motion graphics.

# final reel quality verification marker

# Syntax verification marker.
