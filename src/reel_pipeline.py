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
from post_bank import get_bank_rows
from telegram_bot import send_video, send_message
from free_media import cached_fallback_assets, fetch_openverse_images, fetch_wikimedia_images, generate_legal_cards
from utils import now_cairo, parse_date

MPT_REPO = "https://github.com/harry0703/MoneyPrinterTurbo.git"
MPT_REF = "v1.3.7"
OUTPUT_ROOT = Path("generated/reels")


def choose_row(
    rows: list[dict[str, str]],
    source_context: dict[str, Any] | None = None,
) -> tuple[int, dict[str, str]] | None:
    """Select only the row explicitly locked by the core publishing worker."""
    if source_context:
        try:
            target_number = int(source_context.get("row_number"))
        except (TypeError, ValueError):
            return None
        index = target_number - 2
        if index < 0 or index >= len(rows):
            print(f"Reel source row {target_number} is outside the current Sheet range.")
            return None
        row = rows[index]
        source_id = str(source_context.get("source_id", "") or "").strip()
        row_id = str(row.get("ID", "") or "").strip()
        if source_id and row_id and source_id != row_id:
            print(f"Reel source mismatch: locked ID={source_id}, Sheet ID={row_id}. Refusing to guess another row.")
            return None
        fb_ok = str(row.get("Facebook Status", "") or "").strip().upper() == "PUBLISHED"
        li_ok = str(row.get("LinkedIn Status", "") or "").strip().upper() == "PUBLISHED"
        if not (fb_ok or li_ok):
            print(f"Reel source row {target_number} has no successful social publication.")
            return None
        if not str(row.get("المحتوى", "")).strip():
            print(f"Reel source row {target_number} has no post content.")
            return None
        reel_status = str(row.get("Reel Status", "")).strip().upper()
        reel_file = str(row.get("Reel File", "")).strip()
        if reel_status == "PUBLISHED":
            print(f"Reel source row {target_number} already has Reel Status=PUBLISHED.")
            return None
        if reel_status in {"GENERATING", "REVIEW", "APPROVED"} and reel_file:
            # Reuse only when the stored file belongs to this row AND actually exists.
            if str(source_id or "").strip() in reel_file and Path(reel_file).is_file():
                print(f"Reel source row {target_number} already has a valid Reel file.")
                return None
            if str(source_id or "").strip() in reel_file and not Path(reel_file).is_file():
                print(f"Reel source row {target_number} has a stale/missing Reel file; regenerating.")
        locked_topic = str(source_context.get("topic", "") or "").strip()
        if locked_topic and locked_topic != str(row.get("الموضوع", "") or "").strip():
            print(f"Reel source topic mismatch for row {target_number}; refusing to guess another row.")
            return None
        print(f"Reel source locked to exact published row {target_number}.")
        return target_number, row

    print("Reel generator: no locked source context; refusing to select an arbitrary published row.")
    return None


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


def generate_local_egyptian_tts_audio(script: str, output_path: Path, emotion_map: list[dict[str, Any]] | None = None) -> Path:
    """Lightweight local Arabic fallback. Gemini remains the primary voice."""
    clean = prepare_tts_script(script)
    # Keep the fallback dependency-free: espeak-ng is installed by the Reel job.
    # This is only a resilience path when Gemini TTS is unavailable.
    try:
        subprocess.run(
            ["espeak-ng", "-v", "ar", "-s", "145", "-p", "45", "-w", str(output_path), clean],
            check=True,
            timeout=120,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        raise RuntimeError(f"Arabic local TTS fallback failed: {exc}") from exc
    if not output_path.is_file():
        raise RuntimeError("Arabic local TTS fallback produced no audio file.")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    duration = float(probe.stdout.strip() or "0")
    if duration < 20:
        raise RuntimeError(f"Local Arabic TTS fallback produced too little audio: {duration:.1f}s")
    print(f"Local Arabic TTS fallback succeeded: duration={duration:.1f}s")
    return output_path

def generate_gemini_tts_audio_unbounded(
    api_key: str,
    script: str,
    emotion_map: list[dict[str, Any]],
    output_path: Path,
    min_seconds: float = 1.0,
    max_seconds: float = 10.0,
) -> Path:
    """Gemini TTS helper for short brand stings; separate from long Reel narration validation."""
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for short TTS.")
    clean = prepare_tts_script(script)
    content = [{
        "type": "text",
        "text": sentence,
        "annotations": [{
            "type": "speech_metadata",
            "style": "Egyptian Arabic, mature male legal presenter, confident memorable sign-off, natural Cairo delivery",
        }],
    } for sentence in [s.strip() for s in re.split(r"(?<=[؟!.])\s+", clean) if s.strip()]]
    payload = {
        "model": os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts"),
        "input": [{"type": "user_input", "content": content}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": os.getenv("GEMINI_TTS_VOICE", "Orus")}]},
    }
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        data = json.loads(response.read().decode("utf-8"))
    encoded = ((data.get("interaction") or {}).get("output_audio") or {}).get("data")
    if not encoded:
        for step in data.get("steps") or (data.get("interaction") or {}).get("steps") or []:
            for item in step.get("content") or []:
                if item.get("type") == "audio" and item.get("data"):
                    encoded = item["data"]
                    break
            if encoded:
                break
    if not encoded:
        raise RuntimeError(f"Gemini short TTS returned no audio: {str(data)[:1200]}")
    output_path.write_bytes(base64.b64decode(encoded))
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    duration = float(probe.stdout.strip() or "0")
    if duration < min_seconds or duration > max_seconds:
        raise RuntimeError(f"Gemini short TTS duration outside {min_seconds}-{max_seconds}s: {duration:.1f}s")
    return output_path


def generate_local_egyptian_tts_audio_unbounded(
    script: str,
    output_path: Path,
    min_seconds: float = 1.0,
    max_seconds: float = 10.0,
) -> Path:
    clean = prepare_tts_script(script)
    subprocess.run(
        ["espeak-ng", "-v", "ar", "-s", "145", "-p", "45", "-w", str(output_path), clean],
        check=True, timeout=120, capture_output=True, text=True,
    )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    duration = float(probe.stdout.strip() or "0")
    if duration < min_seconds or duration > max_seconds:
        raise RuntimeError(f"Local short TTS duration outside {min_seconds}-{max_seconds}s: {duration:.1f}s")
    return output_path


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
        # Current Interactions responses expose audio as step content. Keep the
        # legacy field above for compatibility, but prefer the actual returned
        # audio step when output_audio is absent.
        for step in data.get("steps") or (data.get("interaction") or {}).get("steps") or []:
            for item in step.get("content") or []:
                if item.get("type") == "audio" and item.get("data"):
                    encoded = item["data"]
                    break
            if encoded:
                break
    if not encoded:
        raise RuntimeError(f"Gemini TTS returned no audio: {str(data)[:1500]}")
    try:
        output_path.write_bytes(base64.b64decode(encoded))
    except Exception as exc:
        raise RuntimeError(f"Invalid Gemini TTS audio payload: {exc}") from exc
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)], capture_output=True, text=True, check=True, timeout=30)
    duration = float(probe.stdout.strip() or "0")
    if duration < 45 or duration > 80:
        raise RuntimeError(f"Gemini TTS duration outside Reel target: {duration:.1f}s")
    return output_path


def add_motion_graphics_layer(input_video: Path, output_video: Path, topic: str = "", logo_path: str = "", slogan_audio: Path | None = None) -> Path:
    """Use purposeful camera motion on real scenes; no generic floating graphics or editorial titles."""
    work_dir = output_video.parent / "motion"
    work_dir.mkdir(parents=True, exist_ok=True)
    from PIL import Image, ImageDraw, ImageFont
    logo = Path(logo_path) if logo_path else Path(os.getenv("BRAND_LOGO_PATH", "لوجو اسال محمود 3دي.png"))
    endcard = work_dir / "brand_endcard.mp4"
    img = Image.new("RGB", (1080, 1920), (8, 13, 22))
    draw = ImageDraw.Draw(img)
    if logo.is_file():
        try:
            mark = Image.open(logo).convert("RGBA")
            mark.thumbnail((760, 760), Image.Resampling.LANCZOS)
            img.paste(mark, ((1080-mark.width)//2, 390), mark)
        except Exception as exc:
            print(f"Brand logo could not be loaded: {exc}")
    font_path = "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"
    font = ImageFont.truetype(font_path, 62) if Path(font_path).exists() else ImageFont.load_default()
    small = ImageFont.truetype(font_path, 43) if Path(font_path).exists() else ImageFont.load_default()
    import arabic_reshaper
    from bidi.algorithm import get_display
    rtl = lambda value: get_display(arabic_reshaper.reshape(value))
    draw.text((540, 1220), rtl("اسأل محمود - مستشار قانوني للشركات"), font=font, anchor="mm", fill="white")
    draw.text((540, 1340), rtl("وفي النهاية خليك دايما فاكر ... اسأل محمود"), font=small, anchor="mm", fill=(215,225,240))
    draw.ellipse((455, 1430, 625, 1600), fill=(24,119,242))
    fbfont = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 125)
    draw.text((540, 1515), "f", font=fbfont, anchor="mm", fill="white")
    end_png = work_dir / "brand_endcard.png"
    img.save(end_png, quality=95)
    if slogan_audio and slogan_audio.is_file():
        subprocess.run(["ffmpeg","-y","-loop","1","-i",str(end_png),"-i",str(slogan_audio),"-t","3.0",
            "-vf","scale=1080:1920,zoompan=z='min(zoom+0.0008,1.025)':d=1:s=1080x1920:fps=30",
            "-af","apad=pad_dur=3,atrim=duration=3","-map","0:v:0","-map","1:a:0",
            "-c:v","libx264","-preset","veryfast","-crf","18","-c:a","aac","-b:a","160k","-shortest",str(endcard)],check=True,timeout=180)
    else:
        subprocess.run(["ffmpeg","-y","-loop","1","-i",str(end_png),"-f","lavfi","-i","anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t","3.0","-vf","scale=1080:1920,zoompan=z='min(zoom+0.0008,1.025)':d=1:s=1080x1920:fps=30",
            "-c:v","libx264","-preset","veryfast","-crf","18","-c:a","aac","-b:a","160k","-shortest",str(endcard)],check=True,timeout=180)
    base = work_dir / "base_motion.mp4"
    vf = "scale=1160:2060:force_original_aspect_ratio=increase,crop=1080:1920:x='40+20*sin(t*0.22)':y='70+24*cos(t*0.18)',eq=contrast=1.03:saturation=1.04"
    subprocess.run(["ffmpeg","-y","-i",str(input_video),"-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","19","-c:a","copy","-movflags","+faststart",str(base)],check=True,timeout=900)
    styled = work_dir / "styled.mp4"
    concat_list = work_dir / "concat.txt"
    concat_list.write_text(f"file '{base.resolve()}'\\nfile '{endcard.resolve()}'\\n", encoding="utf-8")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat_list),"-c:v","libx264","-preset","veryfast","-crf","19","-c:a","aac","-b:a","160k","-movflags","+faststart",str(styled)],check=True,timeout=900)
    shutil.copy2(styled, output_video)
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
    fallback = (os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash") or "").strip()
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


def build_fast_fallback_reel(
    scenes: list[Path],
    audio_path: Path,
    output_video: Path,
    duration_seconds: int = 56,
) -> None:
    """Build a deterministic review Reel without MoneyPrinterTurbo."""
    if len(scenes) < 4:
        raise RuntimeError("Fast Reel fallback requires at least 4 scenes.")
    output_video.parent.mkdir(parents=True, exist_ok=True)
    selected = scenes[:8]
    per_scene = max(4.0, duration_seconds / len(selected))
    concat_file = output_video.parent / "fast_concat.txt"
    lines = []
    for scene in selected:
        path = str(scene.resolve()).replace("'", "'\\\\''")
        lines.append("file '" + path + "'")
        lines.append(f"duration {per_scene:.3f}")
    lines.append("file '" + str(selected[-1].resolve()).replace("'", "'\\\\''") + "'")
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-i", str(audio_path),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p",
        "-t", str(duration_seconds),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        str(output_video),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=240, check=False)
    if result.returncode != 0 or not output_video.is_file():
        raise RuntimeError("Fast Reel fallback failed: " + (result.stderr or result.stdout)[-4000:])
    print(f"Fast Reel fallback created: {output_video}")


def main() -> int:
    cfg = load_reel_config()
    service = create_service(cfg["service_account_info"])
    sheet_name = cfg["sheet_range"].split("!", 1)[0]
    ensure_headers(service, cfg["sheet_id"], sheet_name)
    values = get_values(service, cfg["sheet_id"], cfg["sheet_range"])
    print("Reel Sheet source: range=" + str(cfg["sheet_range"]) + " rows_loaded=" + str(max(0, len(values) - 1)) + " headers_width=" + str(len(values[0]) if values else 0))
    rows = [row_to_dict(row) for row in values[1:]]
    source_path = Path("generated/reel_source.json")
    source_context = None
    if source_path.is_file():
        try:
            source_context = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Reel generator: invalid locked source context: {exc}")
            source_context = None

    if source_context is None and os.getenv("REEL_RECOVERY", "").strip().lower() in {"1", "true", "yes", "on"}:
        now = now_cairo()
        today = now.date().isoformat()
        rows = [row_to_dict(row) for row in values[1:]]
        today_prefix = today.replace("-", "") + "-"
        today_id_matches = [(idx + 2, str(row.get("ID", "")).strip()) for idx, row in enumerate(rows) if str(row.get("ID", "")).strip().startswith(today_prefix)]
        print("Reel recovery source check: cairo_now=" + now.isoformat() + " today_id_matches=" + str(today_id_matches))
        recovered = []
        for row_number, row in enumerate(rows, start=2):
            source_id = str(row.get("ID", "")).strip()
            is_today_by_id = source_id.startswith(today_prefix)
            is_today_by_date = parse_date(row.get("تاريخ النشر", "")) == now_cairo().date()
            if not (is_today_by_id or is_today_by_date):
                continue
            if not str(row.get("المحتوى", "")).strip():
                # Recover only by the immutable source ID; never borrow another row's text.
                source_id = str(row.get("ID", "")).strip()
                if source_id:
                    try:
                        bank_rows = get_bank_rows(service, cfg["sheet_id"])
                        matches = [b for b in bank_rows if str(b.get("Source Row ID", "") or b.get("ID", "")).strip() == source_id]
                        if matches:
                            recovered_post = str(matches[-1].get("المحتوى", "") or matches[-1].get("Content", "") or "").strip()
                            if recovered_post:
                                row["المحتوى"] = recovered_post
                                update_row(service, cfg["sheet_id"], sheet_name, row_number, {"المحتوى": recovered_post})
                                print(f"Reel recovery: restored missing Sheet content from PostBank for row {row_number}.")
                    except Exception as exc:
                        print(f"Reel recovery: PostBank content restore unavailable for row {row_number}: {exc}")
                if not str(row.get("المحتوى", "")).strip():
                    continue
            if not (
                str(row.get("Facebook Status", "")).strip().upper() == "PUBLISHED"
                or str(row.get("LinkedIn Status", "")).strip().upper() == "PUBLISHED"
            ):
                continue
            reel_status = str(row.get("Reel Status", "")).strip().upper()
            reel_file = str(row.get("Reel File", "")).strip()
            if reel_status == "PUBLISHED":
                continue
            if reel_status == "GENERATING" and reel_file:
                continue
            if reel_status in {"REVIEW", "APPROVED"} and reel_file:
                continue
            recovered.append((row_number, row))
        if not recovered:
            # Google Sheets can briefly expose the pre-publication state to a downstream job.
            # Re-read once before refusing the exact current-day row; never fall back to older rows.
            import time
            time.sleep(5)
            values = get_values(service, cfg["sheet_id"], cfg["sheet_range"])
            rows = [row_to_dict(row) for row in values[1:]]
            print("Reel recovery retry: re-read Sheet after 5s.")
            for row_number, row in enumerate(rows, start=2):
                source_id = str(row.get("ID", "")).strip()
                if not source_id.startswith(today_prefix):
                    continue
                fb_status = str(row.get("Facebook Status", "")).strip().upper()
                li_status = str(row.get("LinkedIn Status", "")).strip().upper()
                content_ok = bool(str(row.get("المحتوى", "")).strip())
                reel_status = str(row.get("Reel Status", "")).strip().upper()
                reel_file = str(row.get("Reel File", "")).strip()
                print(f"Reel recovery retry row={row_number} id={source_id} fb={fb_status} li={li_status} content={content_ok} reel={reel_status} file={bool(reel_file)}")
                if content_ok and (fb_status == "PUBLISHED" or li_status == "PUBLISHED") and reel_status != "PUBLISHED":
                    if not (reel_status in {"GENERATING", "REVIEW", "APPROVED"} and reel_file):
                        recovered.append((row_number, row))
            diagnostics = []
            for row_number, row in enumerate(rows, start=2):
                source_id = str(row.get("ID", "")).strip()
                fb_status = str(row.get("Facebook Status", "")).strip().upper()
                li_status = str(row.get("LinkedIn Status", "")).strip().upper()
                content_ok = bool(str(row.get("المحتوى", "")).strip())
                daily_id = source_id.startswith(today_prefix)
                reel_status = str(row.get("Reel Status", "")).strip().upper()
                reel_file = str(row.get("Reel File", "")).strip()
                existing_file = bool(reel_file and source_id and source_id in reel_file and Path(reel_file).is_file())
                diagnostics.append(
                    f"row={row_number} id={source_id} daily_id={daily_id} fb={fb_status} li={li_status} "
                    f"content={content_ok} reel={reel_status} file_exists={existing_file}"
                )
                if not (daily_id or parse_date(row.get("تاريخ النشر", "")) == now_cairo().date()) or not content_ok or not (fb_status == "PUBLISHED" or li_status == "PUBLISHED"):
                    continue
                if reel_status == "PUBLISHED":
                    continue
                if existing_file:
                    continue
                recovered.append((row_number, row))
            if not recovered:
                print("Reel recovery diagnostics: " + " | ".join(diagnostics[-12:]))

        if recovered:
            row_number, row = recovered[-1]
            source_context = {
                "row_number": row_number,
                "source_id": str(row.get("ID", "")).strip(),
                "topic": str(row.get("الموضوع", "")).strip(),
            }
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(json.dumps(source_context, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Reel recovery: rebuilt lock for today's published row {row_number}.")
        else:
            print("Reel recovery: no eligible published row for today.")
            return 0

    if source_context is None:
        print("Reel generator: no locked source from the core publishing worker; refusing to choose another row.")
        return 0
    selected = choose_row(rows, source_context)
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

    review_video_delivered = False
    try:
        print(f"REEL_STAGE start row={row_number} topic={topic!r}")
        brief = make_brief(cfg["gemini_api_key"], os.getenv("GEMINI_MODEL", "gemini-3.6-flash"), topic, post)
        print("REEL_STAGE brief=ok")
        output_dir.mkdir(parents=True, exist_ok=True)
        brief["script"] = prepare_tts_script(brief["script"])
        (output_dir / "script.txt").write_text(brief["script"], encoding="utf-8")
        (output_dir / "reel_plan.json").write_text(json.dumps({"topic": topic, **brief}, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "delivery_map.json").write_text(json.dumps(brief.get("emotion_map", []), ensure_ascii=False, indent=2), encoding="utf-8")

        scene_dir = output_dir / "scenes"
        print("REEL_STAGE media=fetch_openverse")
        scenes = fetch_openverse_images(brief["video_terms"], scene_dir)
        print(f"REEL_STAGE openverse_count={len(scenes)}")
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

        print("REEL_STAGE tts=start")
        tts_audio = output_dir / "voice-gemini.wav"
        # Never send a low-quality robotic local voice to the reviewer.
        # Gemini TTS is the approved Reel voice. If it is unavailable/quota-limited,
        # fail before video delivery instead of silently substituting espeak.
        try:
            generate_gemini_tts_audio(cfg["gemini_api_key"], brief["script"], brief.get("emotion_map", []), tts_audio)
            print("REEL_STAGE tts=gemini_ok")
        except Exception as gemini_tts_exc:
            raise RuntimeError(
                "Reel voice generation unavailable; refusing to send robotic/local TTS. "
                f"Gemini TTS error: {gemini_tts_exc}"
            ) from gemini_tts_exc

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
            output_video = output_dir / "daily-reel.mp4"
            mpt_ok = False
            try:
                result = subprocess.run(
                    ["uv", "sync", "--frozen"],
                    cwd=mpt,
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=240,
                    check=False,
                )
                if result.returncode == 0:
                    result = subprocess.run(
                        command,
                        cwd=mpt,
                        env=env,
                        text=True,
                        capture_output=True,
                        timeout=300,
                        check=False,
                    )
                if result.returncode == 0:
                    task_videos = sorted(
                        (mpt / "storage" / "tasks" / str(task_id)).glob("final-*.mp4")
                    )
                    if task_videos:
                        raw_video = output_dir / "mpt-base.mp4"
                        shutil.copy2(task_videos[-1], raw_video)
                        slogan_audio = output_dir / "slogan-ask-mahmoud.wav"
                        slogan_text = "وفي النهاية خليك دايما فاكر ... اسأل محمود"
                        slogan_ready = False
                        # The brand sign-off is intentionally short (about 3–8s).
                        # generate_gemini_tts_audio validates long narration, so do
                        # not route a short slogan through that 45–80s gate.
                        try:
                            clean_slogan = prepare_tts_script(slogan_text)
                            generate_gemini_tts_audio_unbounded(
                                cfg["gemini_api_key"],
                                clean_slogan,
                                [{"sentence_index": 1, "delivery_emotion": "warm confident memorable sign-off"}],
                                slogan_audio,
                                min_seconds=1.0,
                                max_seconds=10.0,
                            )
                            slogan_ready = slogan_audio.is_file()
                            print(f"Reel slogan: Gemini ready={slogan_ready}")
                        except Exception as slogan_gemini_exc:
                            print(f"Reel slogan: Gemini unavailable; using local Egyptian TTS: {slogan_gemini_exc}")
                            try:
                                generate_local_egyptian_tts_audio_unbounded(
                                    clean_slogan if 'clean_slogan' in locals() else slogan_text,
                                    slogan_audio,
                                    min_seconds=1.0,
                                    max_seconds=10.0,
                                )
                                slogan_ready = slogan_audio.is_file()
                            except Exception as slogan_local_exc:
                                print(f"Reel slogan disabled; continuing without slogan audio: {slogan_local_exc}")
                                slogan_ready = False
                        try:
                            add_motion_graphics_layer(
                                raw_video,
                                output_video,
                                "",
                                os.getenv("BRAND_LOGO_PATH", "لوجو اسال محمود 3دي.png"),
                                slogan_audio if slogan_ready else None,
                            )
                            print("REEL_STAGE branding=ok")
                        except Exception as branding_exc:
                            # A finished MPT video is already a valid review asset.
                            # Never lose a generated Reel because the optional end-card layer failed.
                            print(f"REEL_STAGE branding_failed_using_raw={branding_exc}")
                            shutil.copy2(raw_video, output_video)
                        raw_video.unlink(missing_ok=True)
                        mpt_ok = output_video.is_file()
                if not mpt_ok:
                    print("MoneyPrinterTurbo bounded run did not finish; using fast FFmpeg fallback.")
            except Exception as mpt_exc:
                print(f"MoneyPrinterTurbo bounded run failed; using fast FFmpeg fallback: {mpt_exc}")

            if not mpt_ok:
                build_fast_fallback_reel(scenes, tts_audio, output_video, duration_seconds=56)

        video_path = output_dir / "daily-reel.mp4"
        # Hard quality gate before Telegram: a review Reel must be a real short
        # video, not a truncated MPT artifact. The narration target is 55–75s.
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, check=True, timeout=30,
        )
        final_duration = float(probe.stdout.strip() or "0")
        if final_duration < 50 or final_duration > 80:
            raise RuntimeError(
                f"Reel quality gate rejected video duration={final_duration:.1f}s; expected 50–80s."
            )
        audio_probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if not audio_probe.stdout.strip():
            raise RuntimeError("Reel quality gate rejected video: no audio stream.")
        print(f"REEL_STAGE quality_gate=ok duration={final_duration:.1f}s audio={audio_probe.stdout.strip()}")
        # Telegram delivery is part of the review contract: do not mark a Reel
        # REVIEW unless the actual MP4 was successfully delivered for approval.
        send_video(
            str(video_path),
            caption=f"🎬 Reel للمراجعة — الصف {row_number}\n\nالموضوع: {topic}",
            reply_markup={
                "inline_keyboard": [[
                    {"text": "✅ اعتماد الريل", "callback_data": f"reel_approve:{row_number}"},
                    {"text": "❌ رفض الريل", "callback_data": f"reel_reject:{row_number}"},
                ]]
            },
        )
        review_video_delivered = True

        review_payload = {
            "Reel Status": "REVIEW",
            "Reel Script": brief["script"],
            "Reel File": str(output_dir / "daily-reel.mp4"),
            "Reel Run ID": os.getenv("GITHUB_RUN_ID", ""),
            "Reel Approval": "",
            "Reel Review": "جاهز للمراجعة اليدوية قبل أي نشر",
            "Reel Last Error": "",
        }
        sheet_saved = False
        last_sheet_error = None
        for attempt in range(1, 6):
            try:
                update_row(service, cfg["sheet_id"], sheet_name, row_number, review_payload)
                sheet_saved = True
                break
            except Exception as exc:
                last_sheet_error = exc
                print(f"Reel review Sheet update attempt {attempt}/5 failed: {exc}")
                if attempt < 5:
                    import time
                    time.sleep(attempt * 3)
        if not sheet_saved:
            (output_dir / "review_pending.json").write_text(
                json.dumps({"row_number": row_number, "status": "REVIEW", "sheet_error": str(last_sheet_error)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"REEL_READY row={row_number} file={video_path} telegram=delivered sheet=retry_pending")
            return 0

        print("REEL_READY row=" + str(row_number) + " file=" + str(video_path) + " telegram=delivered sheet=review")
        return 0
    except Exception as exc:
        if review_video_delivered:
            print(f"Reel video was delivered to Telegram; preserving generated package despite post-delivery failure: {exc}")
            return 0
        try:
            update_row(service, cfg["sheet_id"], sheet_name, row_number, {
                "Reel Status": "FAILED",
                "Reel Last Error": str(exc)[:1500],
            })
        except Exception as sheet_exc:
            print(f"Failed to record Reel FAILED state in Sheet: {sheet_exc}")
        try:
            send_message(
                f"🚨 Reel failed before Telegram delivery\nالصف: {row_number}\nالموضوع: {topic}\nالسبب: {str(exc)[:1200]}"
            )
        except Exception as telegram_exc:
            print(f"Reel failure Telegram notification failed: {telegram_exc}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())


# Reel production verification: Gemini TTS + text-free motion graphics.



# visual quality test marker
