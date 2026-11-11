from __future__ import annotations

import base64
import hashlib
import json
import urllib.request
import os
import re
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Any

from google import genai
from config import load_reel_config
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row
from post_bank import get_bank_rows
from telegram_bot import send_video, send_message
from free_media import cached_fallback_assets, fetch_openverse_images, fetch_wikimedia_images, generate_legal_cards
from utils import now_cairo, parse_date
from social_content import sanitize_social_copy, sanitize_topic

OUTPUT_ROOT = Path("generated/reels")
REEL_MAX_DURATION_SECONDS = 40  # hard cap including full-screen logo and spoken slogan
REEL_MIN_DURATION_SECONDS = 30
REEL_CONTENT_MAX_SECONDS = 34  # reserve 5.5s for branded ending


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
        force_regenerate = os.getenv("REEL_FORCE_REGENERATE", "").strip().lower() in {"1", "true", "yes", "on"}
        force_telegram_review = os.getenv("REEL_FORCE_TELEGRAM_REVIEW", "").strip().lower() in {"1", "true", "yes", "on"}
        # A review decision belongs to the Sheet, not to this runner's ephemeral
        # filesystem. Daily workflows start on fresh machines, so a missing local
        # MP4 must NEVER cause an already-delivered REVIEW Reel to be regenerated
        # and sent again. Only the rejection workflow may regenerate, after it has
        # atomically changed the state to REGENERATING.
        if reel_status in {"REVIEW", "APPROVED", "PUBLISHED"} and not force_regenerate:
            print(f"Reel source row {target_number} is already {reel_status}; waiting for the user's decision and refusing another Telegram delivery.")
            return None
        if reel_status == "REGENERATING" and not force_regenerate:
            print(f"Reel source row {target_number} is already locked for regeneration; refusing duplicate run.")
            return None
        if reel_status == "PUBLISHED" and not force_regenerate:
            print(f"Reel source row {target_number} already has Reel Status=PUBLISHED.")
            return None
        reel_review = str(row.get("Reel Review", "") or "").strip().upper()
        if not force_regenerate and (reel_review.startswith("TELEGRAM_DELIVERED") or reel_review.startswith("TELEGRAM_SENDING")):
            # A Sheet flag alone is not a durable delivery proof. The final MP4
            # must still exist at the row-owned path; otherwise the lock is stale
            # (for example after a failed render before Telegram delivery).
            delivery_file_exists = bool(reel_file and source_id and source_id in reel_file and Path(reel_file).is_file())
            if delivery_file_exists:
                print(f"Reel source row {target_number} has a valid Telegram delivery lock; refusing duplicate generation/send.")
                return None
            print(f"Reel source row {target_number} has a stale Telegram lock without a valid final MP4; clearing lock for regeneration.")
        if not force_regenerate and reel_status in {"GENERATING", "REVIEW", "APPROVED"} and reel_file:
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
    out = re.sub(r"https?://\S+", "", out, flags=re.I)
    out = re.sub(r"[@#%*_{}\[\]<>|\\/]+", " ", out)
    out = re.sub(r"\b(?:API|SEO|GEO|CTA|FAQ|URL)\b", "", out, flags=re.I)
    out = re.sub(r"\s+", " ", out).strip(" .،؛:|-")
    return out


def _clean_tts_text(text: str) -> str:
    out = egyptian_spoken_text(text)
    out = out.replace("(", " ").replace(")", " ").replace("…", "...").replace("؛", "،")
    out = re.sub(r"\.{2,}", "...", out)
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"\d+", " ", out)
    if not out:
        raise RuntimeError("TTS script is empty after sanitization.")
    return out


def prepare_tts_script(text: str) -> str:
    """Clean spoken Egyptian Arabic; do not inject machine-generated diacritics."""
    return _clean_tts_text(text)


def prepare_neural_tts_script(text: str) -> str:
    return _clean_tts_text(text)

def _urlopen_with_retry(request, *, timeout: int, attempts: int = 3):
    """Retry transient TLS disconnects without repeating downstream Telegram actions."""
    import time
    import ssl
    import socket
    from urllib.error import URLError

    last_error = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except (URLError, ssl.SSLError, socket.timeout, TimeoutError, EOFError, ConnectionError) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = min(2 ** (attempt - 1), 8)
            print(f"Transient TLS/network failure ({type(exc).__name__}); retry {attempt + 1}/{attempts} in {delay}s: {exc}")
            time.sleep(delay)
    raise RuntimeError(f"External TLS/network request failed after {attempts} attempts: {last_error}") from last_error


def _refresh_google_credentials_with_retry(credentials, attempts: int = 3) -> None:
    from google.auth.transport.requests import Request
    import time

    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            credentials.refresh(Request())
            if not credentials.token:
                raise RuntimeError("Google Cloud credentials refresh returned no token.")
            return
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = min(attempt * 2, 6)
            print(f"Google credential refresh failed; retry {attempt + 1}/{attempts} in {delay}s: {exc}")
            time.sleep(delay)
    raise RuntimeError(f"Google Cloud credentials refresh failed after {attempts} attempts: {last_error}") from last_error


def generate_google_cloud_arabic_tts_audio(service_account_info: dict[str, Any], script: str, output_path: Path) -> Path:
    """High-quality Arabic fallback using the existing Google service account."""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    _refresh_google_credentials_with_retry(credentials)

    clean = prepare_tts_script(script)
    payload = {
        "input": {"text": clean},
        "voice": {
            "languageCode": os.getenv("GOOGLE_TTS_LANGUAGE", "ar-XA"),
            "name": os.getenv("GOOGLE_TTS_VOICE", "ar-XA-Wavenet-D"),
        },
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "speakingRate": float(os.getenv("GOOGLE_TTS_SPEAKING_RATE", "0.96")),
            "pitch": float(os.getenv("GOOGLE_TTS_PITCH", "0.0")),
        },
    }
    req = urllib.request.Request(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"},
        method="POST",
    )
    with _urlopen_with_retry(req, timeout=120, attempts=3) as response:
        data = json.loads(response.read().decode("utf-8"))
    encoded = str(data.get("audioContent") or "")
    if not encoded:
        raise RuntimeError(f"Google Cloud TTS returned no audio: {str(data)[:1200]}")
    output_path.write_bytes(base64.b64decode(encoded))
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    duration = float(probe.stdout.strip() or "0")
    if duration < 22 or duration > REEL_CONTENT_MAX_SECONDS:
        raise RuntimeError(f"Google Cloud TTS narration must be 22–34 seconds before the 5.5-second logo ending; got {duration:.1f}s")
    print(f"Google Cloud Arabic TTS succeeded: duration={duration:.1f}s")
    return output_path


def _media_duration(path: Path) -> float:
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True, check=True, timeout=30)
    return float(probe.stdout.strip() or "0")

def fit_reel_narration_duration(path: Path, target_seconds: float | None = None) -> Path:
    """QA only. Never speed up natural Egyptian narration."""
    duration = _media_duration(path)
    minimum = 22.0
    maximum = float(REEL_CONTENT_MAX_SECONDS)
    if duration < minimum:
        raise RuntimeError("Reel narration is too short: %.1fs; configured minimum is %.1fs." % (duration, minimum))
    if duration > maximum:
        raise RuntimeError("Reel narration exceeds configured hard maximum: %.1fs > %.1fs." % (duration, maximum))
    print("Reel narration QA passed without speed change: duration=%.1fs" % duration)
    return path

def _normalize_reel_audio_duration(path: Path, target_max: float | None = None) -> Path:
    """Keep Egyptian neural speech at natural speed; never use atempo compression."""
    duration = _media_duration(path)
    minimum = 22.0
    maximum = min(float(target_max), float(REEL_CONTENT_MAX_SECONDS)) if target_max is not None else float(REEL_CONTENT_MAX_SECONDS)
    if duration < minimum:
        raise RuntimeError("Egyptian Neural TTS audio is too short: %.1fs; configured minimum is %.1fs." % (duration, minimum))
    if duration > maximum:
        raise RuntimeError("Egyptian Neural TTS audio exceeds configured hard maximum: %.1fs > %.1fs." % (duration, maximum))
    print("Egyptian Neural TTS ready without speed change: duration=%.1fs" % duration)
    return path

def generate_google_cloud_short_arabic_tts_audio(service_account_info: dict[str, Any], script: str, output_path: Path) -> Path:
    """Generate a short brand sign-off using the existing Google Cloud TTS credentials."""
    from google.oauth2 import service_account
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    _refresh_google_credentials_with_retry(credentials)
    clean = prepare_tts_script(script)
    payload = {
        "input": {"text": clean},
        "voice": {
            "languageCode": os.getenv("GOOGLE_TTS_LANGUAGE", "ar-XA"),
            "name": os.getenv("GOOGLE_TTS_VOICE", "ar-XA-Wavenet-D"),
        },
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "speakingRate": float(os.getenv("GOOGLE_TTS_SPEAKING_RATE", "0.96")),
            "pitch": float(os.getenv("GOOGLE_TTS_PITCH", "0.0")),
        },
    }
    req = urllib.request.Request(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"},
        method="POST",
    )
    with _urlopen_with_retry(req, timeout=120, attempts=3) as response:
        data = json.loads(response.read().decode("utf-8"))
    encoded = str(data.get("audioContent") or "")
    if not encoded:
        raise RuntimeError(f"Google Cloud TTS returned no short audio: {str(data)[:800]}")
    output_path.write_bytes(base64.b64decode(encoded))
    duration = _media_duration(output_path)
    if duration < 1.0 or duration > 10.0:
        raise RuntimeError(f"Google Cloud short TTS duration invalid: {duration:.1f}s")
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
    with _urlopen_with_retry(req, timeout=180, attempts=3) as response:
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


def generate_gemini_tts_audio(api_key: str, script: str, emotion_map: list[dict[str, Any]], output_path: Path) -> Path:
    """Generate the Reel narration with Gemini 3.8 Flash TTS."""
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for Reel narration.")
    clean = prepare_tts_script(script)
    # Sentence-level metadata controls delivery without being spoken. The model
    # supports Egyptian Arabic and style instructions in speech_metadata.
    sentences = [s.strip() for s in re.split(r"(?<=[؟!.])\s+", clean) if s.strip()]
    content = []
    for idx, sentence in enumerate(sentences, start=1):
        emotion = "confident, engaging Egyptian Arabic, clear diction, reassuring legal authority"
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
                    "Natural everyday Egyptian Arabic, mature male legal presenter, engaging and trustworthy; "
                    + emotion
                    + "; confident but reassuring, crisp diction, conversational Cairo accent, natural pauses, no monotone and not a newsreader"
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
        with _urlopen_with_retry(req, timeout=300, attempts=3) as response:
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
    if duration < 22 or duration > REEL_CONTENT_MAX_SECONDS:
        raise RuntimeError(f"Gemini TTS narration must be 22–34 seconds before the 5.5-second logo ending; got {duration:.1f}s")
    return output_path



def _visual_topic_family(topic: str) -> str:
    """Resolve one authoritative visual family from the public legal topic."""
    value = " ".join(str(topic or "").split()).casefold()
    families = [
        ("nursery_surveillance", ("حضانات", "حضانة", "دار حضانة", "روضة أطفال", "رياض الأطفال")),
        ("secret_threat", ("تهديد", "إفشاء", "افشاء", "أسرار", "اسرار", "ابتزاز", "مساومة")),
        ("unauthorized_recording", ("تصوير", "التصوير", "كاميرا", "تسجيل دون إذن", "تصوير دون إذن", "خصوصية الصورة")),
        ("harassment", ("تحرش", "مضايقة", "ملاحقة")),
        ("employment", ("عمل", "عامل", "عمال", "موظف", "فصل", "مرتب", "راتب", "أجر", "استقالة")),
        ("family", ("طلاق", "خلع", "نفقة", "حضانة", "رؤية", "زواج", "أسرة", "اسرة")),
        ("public_utility", ("المرفق العام", "المرافق العامة", "مرفق عام", "المرفق الاقتصادي", "مرفق اقتصادي", "المرافق الاقتصادية", "خدمة عامة", "الخدمات العامة")),
        ("companies", ("شركة", "شركات", "شريك", "شراكة", "تأسيس", "مساهم")),
        ("contracts", ("عقد", "عقود", "تعاقد", "فسخ", "إخلال", "اتفاق")),
        ("rent", ("إيجار", "ايجار", "مؤجر", "مستأجر", "طرد", "إخلاء")),
        ("payments", ("شيك", "إيصال", "ايصال", "دفع", "تحويل", "مديونية", "مبلغ")),
        ("inheritance", ("ميراث", "تركة", "ورثة", "وصية")),
        ("compensation", ("تعويض", "إصابة", "اصابة", "ضرر", "مسؤولية مدنية")),
        ("criminal", ("جريمة", "جنائي", "سرقة", "ضرب", "قتل", "سب", "قذف", "نصب", "احتيال")),
    ]
    for family, terms in families:
        if any(term in value for term in terms):
            return family
    return "general"


_VISUAL_SCENES = {
    "secret_threat": [
        "A close-up of a smartphone receiving a threatening private message; all screen content blurred and unreadable, present-day home setting.",
        "A person carefully preserving the original threatening message and its timestamp on a smartphone.",
        "A smartphone beside a printed digital-message evidence record and a dated incident timeline.",
        "A locked drawer containing confidential personal files, emphasizing protection of private information.",
        "A laptop showing a password-protected private folder, with no readable screen text.",
        "A close-up of a phone notification and message metadata, with all words obscured.",
        "A person documenting the date and time of a sequence of private messages.",
        "A private office desk with a secured phone and confidential file folder, contemporary documentary realism.",
    ],
    "nursery_surveillance": [
        "A realistic wide interior photograph of a modern daycare nursery classroom after hours, empty of people, with a clearly visible CCTV dome camera mounted high in the corner and small chairs and toys below.",
        "A close-up documentary photograph of a professional CCTV security camera installed on the ceiling of a clean daycare hallway, nursery rooms visible in the background, no people.",
        "A realistic view from inside a daycare reception area showing a security monitor with several blurred camera feeds and a CCTV camera mounted near the entrance, no people or readable text.",
        "A modern nursery playroom photographed from a corner security-camera viewpoint, empty room, child-sized furniture and toys visible, camera housing in the upper foreground.",
        "A technician's hands installing a small CCTV dome camera on the ceiling of an empty daycare classroom, no faces, no children, no readable text.",
        "A realistic close-up of a CCTV camera and its cable installation in a daycare corridor, with the nursery entrance softly visible behind it.",
        "A daycare administration desk with a CCTV monitor showing blurred empty-room camera feeds, a closed compliance folder and no readable writing.",
        "A wide documentary photograph of a modern nursery building entrance with visible security cameras and a clean reception area, no identifiable people.",
    ],
    "unauthorized_recording": [
        "A modern smartphone camera pointed toward a person in a public place, with the person's face not visible.",
        "A close-up of a phone camera recording indicator in a contemporary public setting.",
        "A person noticing a smartphone being used to record them without consent, faces kept out of frame.",
        "A privacy-focused scene showing a smartphone camera and a person creating distance from the device.",
        "A CCTV-style camera mounted in a modern building corridor, clearly distinct from a phone recording.",
        "A smartphone beside a written incident timeline about recording without permission, no readable text.",
        "A modern public-space scene with a phone held up for recording, documentary realism.",
        "A close-up of a phone's camera lens and privacy shutter in a contemporary setting.",
    ],
    "harassment": [
        "A smartphone displaying a blurred unwanted message notification, no readable text.",
        "A person preserving a sequence of unwanted messages on a phone, screen text obscured.",
        "A modern building corridor with a person keeping distance from another person, no faces visible.",
        "A phone beside a dated incident log documenting repeated unwanted contact.",
        "A close-up of a call log with all names and numbers blurred.",
        "A person blocking an unknown contact on a smartphone, interface unreadable.",
        "A public-place scene focused on personal safety and unwanted following, no identifiable faces.",
        "A secured digital evidence folder on a laptop, no readable text.",
    ],
    "employment": [
        "A plain employment contract folder beside blank paper and a capped pen on a modern office desk, no people or readable writing.",
        "A close-up of a simple desk calendar and an attendance-record folder, all dates and text out of focus.",
        "A payroll folder beside a calculator and a bank card, no visible numbers, names, or writing.",
        "A closed employee file beside a small stack of blank leave-request forms, no people or legible text.",
        "A modern HR folder beside a desk calendar and capped pen, clean still-life composition.",
        "A blank leave-request sheet clipped to a plain employment folder, no handwriting or readable text.",
        "A smartphone showing a blurred work-related message notification beside an employee file.",
        "A contemporary workplace desk with employee records and a calendar, documentary realism.",
    ],
    "family": [
        "A private family-law consultation setting with two adult men reviewing a folder, no women or children visible.",
        "A close-up of organized family-court paperwork with all text unreadable.",
        "A calendar and financial records arranged beside a sealed family case file.",
        "A close-up of child-related documents and a closed folder, no child or woman depicted.",
        "A modern desk with marriage or divorce paperwork, text and personal data blurred.",
        "A man reviewing financial records related to family support in a private setting.",
        "A neutral family-court building exterior in contemporary Egypt, no people identifiable.",
        "A secured folder containing family case documents on a modern office desk.",
    ],
    "public_utility": [
        "Photorealistic editorial photograph of a modern municipal water utility building exterior, clear public-service architecture, no logos or readable signs.",
        "Photorealistic industrial scene inside a water treatment plant, large filtration tanks, pipes and clean operational infrastructure.",
        "Photorealistic documentary photograph of an electrical distribution substation with transformers and power lines, safe and orderly infrastructure.",
        "Photorealistic city public transport depot with several modern buses parked in service bays, realistic everyday operation.",
        "Photorealistic street-level scene of technicians repairing a municipal water pipeline, visible pipes and maintenance equipment.",
        "Photorealistic public utility control room with operators monitoring water and electricity network dashboards, all screen text unreadable.",
        "Photorealistic close-up of an industrial water pumping station, large pumps, valves and connected pipes, no text or logos.",
        "Photorealistic municipal public-service reception area with service counters and a few distant visitors, no readable signs or documents.",
    ],
    "companies": [
        "Two adult business partners reviewing a company shareholding agreement at a modern meeting table.",
        "A close-up of company incorporation documents and a corporate registry folder, text unreadable.",
        "A modern boardroom table with company financial statements and a laptop.",
        "Business partners reviewing a shareholder dispute file, no logos or readable text.",
        "A company registration folder beside official-looking blank forms, no invented seals.",
        "A close-up of corporate accounting records and a calculator on a desk.",
        "A modern office meeting focused on a company governance document.",
        "A secured corporate file cabinet with labeled folders but no readable writing.",
    ],
    "contracts": [
        "A close-up of two parties reviewing a printed contract with all text blurred.",
        "A signed document folder beside a pen and laptop on a modern desk.",
        "A person comparing two versions of a business agreement, text unreadable.",
        "A contract file and dated email printouts arranged as evidence of a dispute.",
        "A close-up of a pen beside an unsigned agreement, contemporary office setting.",
        "A modern desk with contract pages and a calendar showing a deadline, no readable text.",
        "Two adult men discussing an agreement at a neutral meeting table.",
        "A secured folder containing contract correspondence and supporting documents.",
    ],
    "rent": [
        "A landlord and tenant's lease documents on a modern apartment table, no people visible.",
        "Apartment keys beside a rental agreement with all text blurred.",
        "A tenant reviewing a rent payment receipt beside a smartphone.",
        "A modern apartment doorway and a sealed rental notice, no readable text.",
        "A close-up of a lease folder and dated payment records.",
        "A property handover scene with keys and an inspection checklist without readable writing.",
        "A modern apartment interior with a rental contract file on a table.",
        "A desk with rent receipts and a calendar, contemporary documentary realism.",
    ],
    "payments": [
        "A close-up of a bank transfer confirmation on a smartphone, all text and amounts blurred.",
        "A cheque and payment receipt arranged on a contemporary desk, no readable text.",
        "A person reviewing a bank statement beside a calculator.",
        "A payment receipt folder and dated transaction records, personal data obscured.",
        "A smartphone beside a bank transfer printout, screen unreadable.",
        "A close-up of a cheque being placed into a secure document folder.",
        "A modern desk with financial evidence and a laptop, no visible logos.",
        "A person organizing proof of payment in a contemporary office.",
    ],
    "inheritance": [
        "A sealed inheritance case folder beside property ownership papers, text unreadable.",
        "A close-up of family estate documents and a calculator on a modern desk.",
        "A property title folder and a family estate inventory sheet with no readable text.",
        "A modern office desk with a will document inside a sealed folder.",
        "A set of property keys beside an estate file, contemporary setting.",
        "A person reviewing estate asset records, hands only and no faces.",
        "A secured cabinet containing inheritance and property documents.",
        "A neutral contemporary office scene with estate paperwork and a calendar.",
    ],
    "compensation": [
        "A damaged vehicle and a carefully documented accident scene, no injured people visible.",
        "A close-up of a repair estimate and insurance correspondence with text blurred.",
        "A damaged household object photographed as evidence for a civil compensation claim.",
        "A medical expense folder and receipts arranged on a desk, no patient depicted.",
        "A car damage inspection with a measuring tool and evidence camera.",
        "A close-up of dated photographs and a compensation claim folder.",
        "A modern office desk with repair invoices and an incident report, text unreadable.",
        "A person organizing evidence of financial loss in a contemporary setting.",
    ],
    "criminal": [
        "A police complaint folder and a smartphone containing blurred evidence, no readable text.",
        "A close-up of a damaged personal item documented as evidence, no violence shown.",
        "A secured evidence bag and incident paperwork on a modern desk.",
        "A person preserving a digital transaction record on a phone, screen blurred.",
        "A modern building entrance with a security camera, documentary realism.",
        "A close-up of a complaint document and dated evidence photographs, text unreadable.",
        "A locked drawer containing a case file and digital evidence device.",
        "A neutral contemporary investigation desk with organized evidence folders.",
    ],
    "general": [
        "A close-up of the specific document or evidence named in the legal topic, with all text unreadable.",
        "A contemporary everyday setting directly related to the legal issue, with no generic courtroom imagery.",
        "A smartphone displaying a blurred notification relevant to the legal topic.",
        "A person organizing the exact records or evidence relevant to the legal topic, no faces visible.",
        "A modern office desk with the specific object or paperwork named in the legal topic.",
        "A close-up of a dated record or receipt relevant to the legal topic, text blurred.",
        "A contemporary home or workplace scene directly illustrating the stated legal issue.",
        "A secured folder containing documents relevant to the stated legal topic.",
    ],
}


def post_visual_terms(post: str, topic: str) -> list[str]:
    """Return eight concrete, topic-specific scenes from the approved legal post."""
    family = _visual_topic_family(topic)
    if family == "general":
        # A generic/empty Sheet title is metadata, not a reason to block a valid
        # published post. Infer the visual family from the approved post itself.
        inferred_family = _visual_topic_family(post)
        if inferred_family != "general":
            family = inferred_family
            print(f"REEL_VISUAL_TOPIC_INFERRED_FROM_POST family={family}")
    scenes = list(_VISUAL_SCENES[family])
    topic_text = " ".join(str(topic or "").split()).casefold()
    post_text = " ".join(str(post or "").split()).casefold()

    # Nursery surveillance is distinct from personal/unauthorized phone recording.
    if family == "nursery_surveillance":
        scenes = [
            "A realistic wide interior photograph of a modern daycare nursery classroom after hours, empty of people, with a clearly visible CCTV dome camera mounted high in the corner and small chairs and toys below.",
            "A close-up documentary photograph of a professional CCTV security camera installed on the ceiling of a clean daycare hallway, nursery rooms visible in the background, no people.",
            "A realistic view from inside a daycare reception area showing a security monitor with several blurred camera feeds and a CCTV camera mounted near the entrance, no people or readable text.",
            "A modern nursery playroom photographed from a corner security-camera viewpoint, empty room, child-sized furniture and toys visible, camera housing in the upper foreground.",
            "A technician's hands installing a small CCTV dome camera on the ceiling of an empty daycare classroom, no faces, no children, no readable text.",
            "A realistic close-up of a CCTV camera and its cable installation in a daycare corridor, with the nursery entrance softly visible behind it.",
            "A daycare administration desk with a CCTV monitor showing blurred empty-room camera feeds, a closed compliance folder and no readable writing.",
            "A wide documentary photograph of a modern nursery building entrance with visible security cameras and a clean reception area, no identifiable people.",
        ]
    # Specific legal situations take precedence over broad criminal-family stock scenes.
    elif family == "criminal" and any(word in topic_text for word in ("التنازل", "التصالح", "صلح")):
        scenes = [
            "A closed criminal case folder beside a separate blank settlement document and a capped pen on a clean office desk, no people, no readable writing, documentary realism.",
            "A close-up of two neatly arranged blank paper sheets representing a settlement and waiver, beside a plain case folder, no text, no hands.",
            "A sealed document envelope placed beside a criminal case folder and a simple calendar with no legible numbers or words.",
            "A police complaint folder beside a separate unsigned blank settlement sheet, clearly distinct documents, no people or readable text.",
            "A tidy desk with a plain document folder, blank paper, and capped pen, visual focus on formal reconciliation paperwork, no hands.",
            "A close-up of an empty document sleeve and neatly stacked blank papers beside a closed case file, no writing or logos.",
            "A neutral office tabletop with a blank settlement sheet clipped to a plain folder, no people, no hands, no symbols.",
            "A secured criminal case folder beside a blank signed-document area with no visible handwriting, clean contemporary still life.",
        ]
    elif family == "secret_threat" and any(word in (topic_text + " " + post_text) for word in ("قتل", "تهديد بالقتل")):
        scenes = [
            "A modern smartphone on a plain desk with a single incoming message bubble completely blurred, visual context of a serious threat, no legible text or people.",
            "A smartphone beside a closed incident-report folder, screen fully defocused and unreadable, clean contemporary still life.",
            "A close-up of a phone with an obscured call-history screen beside a blank evidence note, no readable names, numbers, or writing.",
            "A closed police complaint folder beside a smartphone with its display turned away, no people, no readable text.",
            "A phone and a plain desk calendar with dates not legible, representing a record of repeated threatening calls, no hands.",
            "A secured digital evidence drive beside a closed complaint folder, modern office tabletop, no text or logos.",
            "A smartphone beside a sealed evidence envelope and plain case folder, no visible screen text or people.",
            "A calm home-office tabletop with a secured phone and closed complaint papers, no violence, no people, no readable writing.",
        ]
    # For employment leave/rest topics, use concrete leave and attendance evidence rather than generic workplace portraits.
    elif family == "employment" and any(word in (topic_text + " " + post_text) for word in ("إجاز", "راحة", "عطلة", "راحة أسبوعية")):
        scenes = [
            "A plain employee leave-request form with no readable writing beside a simple desk calendar, a capped pen, and a closed HR folder.",
            "A clean attendance register with all text and dates blurred beside a weekly calendar, no people or hands.",
            "A closed employment folder beside a blank leave-balance sheet and calculator, no legible numbers or writing.",
            "A desk calendar with one day subtly marked by a plain paper tab beside a closed employee file, no readable text.",
            "A blank leave approval sheet clipped to a plain folder beside a capped pen, contemporary office still life.",
            "A weekly planner beside an attendance-record folder and a calculator, all writing out of focus.",
            "A stack of blank leave forms beside a closed HR folder and simple wall clock, no people.",
            "A plain employment file beside a calendar and attendance folder, documentary still-life realism, no readable text.",
        ]
    # Add narrow evidence detail only within the already-selected family.
    elif family == "secret_threat" and any(word in post_text for word in ("واتساب", "رسائل", "رسالة")):
        scenes[5] = "A smartphone beside a blurred private-message thread and timestamp evidence, no readable text."
    elif family == "unauthorized_recording" and any(word in post_text for word in ("مكان عام", "شارع", "مواصلات")):
        scenes[6] = "A contemporary street or public-place scene with a phone recording from a distance, faces not visible."
    elif family == "employment" and any(word in post_text for word in ("أجر", "راتب", "مرتب")):
        scenes[2] = "A payroll statement and dated salary-payment records beside a calculator, all text blurred."
    return scenes


def topic_visual_terms(topic: str) -> list[str]:
    """Return a deterministic, topic-family-specific scene pack."""
    return list(_VISUAL_SCENES[_visual_topic_family(topic)])


def _bound_reel_script(script: str, max_words: int = 140) -> str:
    """Keep spoken copy short enough for a two-minute Reel without speeding up TTS."""
    script = prepare_tts_script(script)
    if len(script.split()) <= max_words:
        return script
    sentences = [s.strip() for s in re.split(r"(?<=[؟!.])\s+", script) if s.strip()]
    if len(sentences) < 3:
        return " ".join(script.split()[:max_words])
    first, last = sentences[0], sentences[-1]
    budget = max_words - len(first.split()) - len(last.split())
    middle = []
    for sentence in sentences[1:-1]:
        count = len(sentence.split())
        if count <= budget:
            middle.append(sentence)
            budget -= count
    result = " ".join([first, *middle, last]).strip()
    return " ".join(result.split()[:max_words]) if len(result.split()) > max_words else result

def make_brief(api_key: str, model: str, topic: str, post: str) -> dict[str, Any]:
    client = genai.Client(api_key=api_key)
    prompt = (
        "Create one Arabic legal short-video package for a modern legal advisory brand. "
        "Use ONLY the supplied reviewed post for spoken legal substance. Never invent legal facts. The TOPIC field is editorial metadata only: NEVER read it aloud, NEVER use it as the opening hook, and NEVER copy its wording into the spoken script unless those exact words are independently necessary and supported by the REVIEWED POST. "
        "Natural everyday Egyptian Arabic as actually spoken in Cairo, not Modern Standard Arabic. Address the viewer directly with natural Egyptian phrasing only where it fits. Sound engaging, reassuring, and confident, not theatrical or salesy. Write for the mouth: contractions, short phrases, clear pauses, and direct address. Add tashkeel only where it improves pronunciation. Avoid robotic legal-news phrasing and MSA connectors such as يجب، ينبغي، حيث، لذلك، وبالتالي، يتعين. Never use hashtags, @, %, slashes, URLs, brackets, markdown, emoji, Latin abbreviations, or unexplained numbers in the spoken script; spell numbers as Arabic words. "
        "MANDATORY STORY DESIGN — write a useful mini-consultation, not a generic legal monologue. Before drafting, silently identify from the reviewed post: (A) the exact real-world problem the viewer faces, (B) the most important legal distinction that changes the answer, (C) the strongest answer the source actually supports, and (D) the next safe action. Every one of these must be unmistakable in the spoken script. "
        + "MANDATORY STRUCTURE in this exact order: (1) First sentence names a concrete risk, costly mistake, or surprising truth that is explicitly supported by the reviewed post; do not use empty hooks such as 'غلطة واحدة ممكن تضيع حقك' unless the post explains exactly how. (2) Ask a sharp, problem-specific question — never a generic 'إيه السؤال اللي لازم تجاوب عليه؟'. (3) Give a real, useful answer immediately in the next sentence — this is the trust-building core, not a teaser. Explicitly explain WHAT the rule or answer is, WHY it applies according to the post, and the key condition or exception if the source mentions one. A viewer should learn something concrete even if they never follow the account. Use a simple if/then distinction when useful. Do not merely paraphrase the question, repeat the hook, say only 'راجع محامي', or hide behind vague wording like 'الموضوع حسب التفاصيل'. If the supplied post does not support a definite legal conclusion, say precisely what fact or document determines the answer and why; never fabricate certainty. (4) Explain the practical consequence in one short sentence, without exaggeration. (5) Give a concrete, safe, source-grounded action the viewer can take now. Avoid generic checklists about preserving all messages/documents unless those are directly relevant to this post. (6) Finish with a strong, specific CTA tied to THIS issue: ask the viewer to comment with one focused question, save the Reel for the exact moment they may need it, or share it with the person who needs this information. No weak 'تابعنا للمزيد' CTA. Never promise individual legal advice. (7) Stop after the CTA; the separately rendered branded ending must remain last and retain the spoken slogan 'خليك فاكر دايما ... اسأل محمود' with the user's logo. Do not put the slogan inside the main script or generate another outro. No headings or labels read aloud. Do not announce the topic or read the Sheet title. "
        + f"Target 25–32 seconds for the spoken body and 55–75 Arabic words maximum. The script must contain 55–75 whitespace-separated words: a strong topic-specific hook, then one clear question, then a direct source-grounded answer, then one strong CTA. Do not speak the slogan in this body; it is generated separately over the original full-screen logo for the final 5.5 seconds. No padding, repeated disclaimer, empty suspense, generic legal warnings, or duplicate conclusions. The final video including slogan must be 30–40 seconds. "
        "Return JSON only with script, video_terms, facebook_caption, linkedin_caption, emotion_map. "
        "video_terms must be 8 highly specific English visual searches, one per scene, tied to the exact reviewed post and sentence. Describe only the concrete action, people, modern objects, documents, workplace, home, phone, or evidence stated in that sentence. Use ordinary present-day settings and documentary realism. Keep backgrounds simple and use only modern props supported by the post. Never add a courtroom or lawyer unless the reviewed post actually describes one. "
        "emotion_map must contain one item per meaningful sentence with sentence_index and delivery_emotion. "
        "Choose delivery emotions that fit the legal subject and sentence function, such as calm_authority, warning, empathy, urgency, reassurance, clarification, or strong_cta. "
        "VOICE DIRECTION: confident, engaging Egyptian male legal presenter; open with alert energy, make the question conversational, deliver the answer with calm authority and a reassuring emphasis on the decisive rule, then end the CTA warmly and decisively. Medium conversational pace, crisp diction, natural Cairo accent and pauses. No monotone, shouting, overacting, or newsreader cadence. The viewer should feel they understood the rule and know what to do, not pressured to follow. "
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
    if not isinstance(data, dict):
        print(f"Gemini Reel response schema mismatch: expected object, received {type(data).__name__}; using deterministic fallback.")
        return deterministic_brief(topic, post)
    if not isinstance(data.get("script"), str) or not data["script"].strip():
        print("Gemini Reel response omitted a usable script; using deterministic fallback.")
        return deterministic_brief(topic, post)
    script = sanitize_social_copy(data["script"].strip())
    script = _bound_reel_script(script, max_words=75)
    # Ignore model-suggested search terms: they can hallucinate a different legal subject.
    # The reviewed public post is the source of truth for the visual family.
    terms = post_visual_terms(post, topic)
    if not 55 <= len(script.split()) <= 75 or len(terms) < 8:
        print("Gemini Reel package failed structural validation; using deterministic fallback.")
        return deterministic_brief(topic, post)
    return {
        "script": script,
        "video_terms": [str(x).strip() for x in terms[:8] if str(x).strip()],
        "facebook_caption": str(data.get("facebook_caption", "")).strip(),
        "linkedin_caption": str(data.get("linkedin_caption", "")).strip(),
        "emotion_map": data.get("emotion_map") if isinstance(data.get("emotion_map"), list) else [],
    }




def deterministic_brief(topic: str, post: str) -> dict[str, Any]:
    """Concise topic-aware fallback matching the same 30–40 second Reel contract."""
    text = " ".join(str(post or "").split())
    sentences = [part.strip() for part in re.split(r"(?<=[؟!.])\s+", text) if part.strip()]
    if not sentences:
        raise RuntimeError("Cannot build Reel script without reviewed post content.")

    # Vary the hook by topic while keeping the claim grounded in the supplied post.
    hooks = [
        "خلي بالك، التفصيلة دي ممكن تغيّر موقفك القانوني. ",
        "قبل ما تتصرف، فيه نقطة مهمة لازم تبقى واضحة. ",
        "الغلط هنا إنك تحكم على الموقف من شكله بس. ",
        "ممكن تكون فاهم حقك صح، لكن ناقصك تفصيل مهم. ",
        "استنى قبل ما تاخد قرار؛ الإجابة مش في الانطباع الأول. ",
    ]
    hook = hooks[sum(ord(ch) for ch in (topic + text[:80])) % len(hooks)].strip()
    topic_words = [w for w in re.findall(r"[ء-ي]+", topic) if len(w) > 2]
    focus = " ".join(topic_words[:4]) or "الموقف ده"
    question = f"إيه اللي يحسم موضوع {focus}؟"
    answer_source = " ".join(sentences[:2])
    answer_source = re.sub(r"https?://\S+", "", answer_source)
    answer_words = answer_source.split()
    answer = " ".join(answer_words[:29]).strip()
    if len(answer_words) > 29:
        answer = answer.rstrip("،؛:") + "، والتفاصيل دي هي اللي تحدد تطبيق القاعدة."
    cta = "اكتب سؤالك المحدد في التعليقات، واحفظ الفيديو قبل ما تاخد خطوة ممكن تندم عليها."
    script = " ".join((hook, question, answer, cta))
    words = script.split()
    if len(words) < 55:
        # Add only source material, never generic padding or unsupported legal rules.
        extra = " ".join(sentences[2:4])
        if extra:
            script = " ".join((hook, question, answer, extra, cta))
    script = _bound_reel_script(script, max_words=75)
    if len(script.split()) < 55:
        raise RuntimeError("Deterministic Reel script is too short to deliver a useful 30–40 second video.")
    spoken_sentences = [x.strip() for x in re.split(r"(?<=[؟!.])\s+", script) if x.strip()]
    emotions = []
    for i, sentence in enumerate(spoken_sentences, start=1):
        emotion = "strong_hook" if i == 1 else "strong_cta" if i == len(spoken_sentences) else "calm_authority"
        emotions.append({"sentence_index": i, "delivery_emotion": emotion})
    return {
        "script": script,
        "video_terms": post_visual_terms(post, topic),
        "facebook_caption": "معلومة قانونية عملية مبنية على الوقائع والمستندات المرتبطة بالموضوع.",
        "linkedin_caption": "معلومة قانونية عملية مبنية على الوقائع والمستندات قبل اتخاذ القرار.",
        "emotion_map": emotions,
        "generation_mode": "deterministic_fallback",
    }


def _probe_video_duration(video_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    return float(result.stdout.strip() or "0")


def main() -> int:
    cfg = load_reel_config()
    service = create_service(cfg["service_account_info"])
    sheet_name = cfg["sheet_range"].split("!", 1)[0]
    ensure_headers(service, cfg["sheet_id"], sheet_name)
    values = get_values(service, cfg["sheet_id"], f"{sheet_name}!A:BZ")
    print("Reel Sheet source: range=" + str(cfg["sheet_range"]) + " rows_loaded=" + str(max(0, len(values) - 1)) + " headers_width=" + str(len(values[0]) if values else 0))
    headers = [str(value or "").strip() for value in values[0]] if values else []
    if not headers or not any(headers):
        raise RuntimeError("Reel Sheet header row is empty; refusing positional column mapping.")
    rows = [row_to_dict(row, headers) for row in values[1:]]
    source_path = Path("generated/reel_source.json")
    source_context = None
    force_telegram_review = os.getenv("REEL_FORCE_TELEGRAM_REVIEW", "").strip().lower() in {"1", "true", "yes", "on"}
    if source_path.is_file():
        try:
            source_context = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Reel generator: invalid locked source context: {exc}")
            source_context = None

    if source_context is None and os.getenv("REEL_RECOVERY", "").strip().lower() in {"1", "true", "yes", "on"}:
        now = now_cairo()
        today = now.date().isoformat()
        headers = [str(value or "").strip() for value in values[0]] if values else []
        if not headers or not any(headers):
            raise RuntimeError("Reel Sheet header row is empty in recovery mode; refusing positional column mapping.")
        rows = [row_to_dict(row, headers) for row in values[1:]]
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
            # Review/approval/generation states belong to an existing Telegram item.
            # Never pick them as fresh source rows merely because their local MP4 is absent.
            if reel_status in {"PUBLISHED", "GENERATING", "REVIEW", "APPROVED", "REGENERATING"}:
                continue
            recovered.append((row_number, row))
        if not recovered:
            # Google Sheets can briefly expose the pre-publication state to a downstream job.
            # Re-read once before refusing the exact current-day row; never fall back to older rows.
            import time
            time.sleep(5)
            values = get_values(service, cfg["sheet_id"], f"{sheet_name}!A:BZ")
            headers = [str(value or "").strip() for value in values[0]] if values else []
            if not headers or not any(headers):
                raise RuntimeError("Reel Sheet header row is empty after recovery re-read.")
            rows = [row_to_dict(row, headers) for row in values[1:]]
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
            # The core publisher may have no due row yet (or today's row may
            # still be scheduled for later). Daily Reel delivery must not depend
            # on the social slot being due at the exact same moment. Recover the
            # newest already-published social post that has no valid Reel file.
            fallback_candidates = []
            for row_number, candidate in enumerate(rows, start=2):
                source_id = str(candidate.get("ID", "") or "").strip()
                post_text = str(candidate.get("المحتوى", "") or "").strip()
                fb_status = str(candidate.get("Facebook Status", "") or "").strip().upper()
                li_status = str(candidate.get("LinkedIn Status", "") or "").strip().upper()
                reel_status = str(candidate.get("Reel Status", "") or "").strip().upper()
                reel_file = str(candidate.get("Reel File", "") or "").strip()
                review = str(candidate.get("Reel Review", "") or "").strip().upper()
                valid_file = bool(reel_file and source_id and source_id in reel_file and Path(reel_file).is_file())
                if not source_id or not post_text or not (fb_status == "PUBLISHED" or li_status == "PUBLISHED"):
                    continue
                # Existing review/approval locks are not fresh Reel work, even when
                # the runner's ephemeral filesystem cannot see their stored MP4.
                if reel_status in {"PUBLISHED", "GENERATING", "REVIEW", "APPROVED", "REGENERATING"} or valid_file:
                    continue
                if review.startswith("TELEGRAM_SENDING"):
                    print(f"Reel recovery fallback skips row {row_number}: Telegram delivery is already in progress.")
                    continue
                fallback_candidates.append((row_number, candidate))
            if fallback_candidates:
                # Catch up in publication order: process the oldest eligible,
                # already-published social post first instead of perpetually
                # favoring the newest row and starving older Reel backlog.
                row_number, candidate = fallback_candidates[0]
                recovered.append((row_number, candidate))
                source_context = {
                    "row_number": row_number,
                    "source_id": str(candidate.get("ID", "") or "").strip(),
                    "topic": str(candidate.get("الموضوع", "") or "").strip(),
                }
                source_path.parent.mkdir(parents=True, exist_ok=True)
                source_path.write_text(json.dumps(source_context, ensure_ascii=False, indent=2), encoding="utf-8")
                print(
                    f"Reel recovery fallback: today's social post is not published yet; "
                    f"locked newest undelivered eligible social row {row_number}."
                )
            else:
                print("Reel recovery: no eligible published row today or in the undelivered recovery queue.")
                return 0

    if source_context is None:
        print("Reel generator: no locked source from the core publishing worker; refusing to choose another row.")
        return 0
    selected = choose_row(rows, source_context)
    if not selected:
        print("Reel generator: no eligible published content row.")
        return 0

    row_number, row = selected
    stale_delivery_lock = False
    stored_review = str(row.get("Reel Review", "") or "").strip().upper()
    stored_file = str(row.get("Reel File", "") or "").strip()
    stored_file_valid = bool(stored_file and source_context.get("source_id", "") and str(source_context.get("source_id", "")).strip() in stored_file and Path(stored_file).is_file())
    if stored_review.startswith("TELEGRAM_DELIVERED") and not stored_file_valid:
        stale_delivery_lock = True
        print(f"Reel row {row_number}: stale Telegram delivery lock detected before generation; new final video will be delivered.")
    topic = sanitize_topic(str(row.get("الموضوع", "")).strip())
    post = sanitize_social_copy(str(row.get("المحتوى", "")).strip())
    # Fail closed when the Sheet title and the actual published post describe different legal subjects.
    # The Reel must never be generated from one source while its title/metadata comes from another.
    topic_family = _visual_topic_family(topic)
    post_family = _visual_topic_family(post)
    if topic_family == "general" and post_family != "general":
        # The published post is the source of truth when the Sheet title is generic.
        # This is a safe inference from the approved content, not a topic substitution.
        topic_family = post_family
        print(f"REEL_SOURCE_TOPIC_INFERRED_FROM_PUBLISHED_POST family={topic_family}")
    elif topic_family != post_family:
        raise RuntimeError(
            "REEL_SOURCE_TOPIC_MISMATCH: Sheet الموضوع and published المحتوى resolve to different legal subjects "
            f"(topic_family={topic_family}, post_family={post_family}); refusing to generate or publish a mismatched Reel."
        )
    visual_topic = topic if _visual_topic_family(topic) != "general" else post[:240]
    run_id = str(os.getenv("GITHUB_RUN_ID", "") or "").strip() or __import__("uuid").uuid4().hex
    safe_source_id = re.sub(r"[^A-Za-z0-9._-]+", "_", str(source_context.get("source_id", "")).strip())
    if not safe_source_id:
        raise RuntimeError("REEL_SOURCE_ID_MISSING: refusing to build a reviewable Reel without an immutable source ID.")
    # Every execution gets an isolated directory; no prior topic can leave an MP4
    # at a path that a later topic or approval can accidentally reuse.
    output_dir = OUTPUT_ROOT / ("row_" + str(row_number)) / safe_source_id / ("run_" + run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Never trust an MP4 left by a previous run; it may be a partial 7-second
    # artifact. Every run must produce and QA its own final file.
    stale_output = output_dir / "daily-reel.mp4"
    stale_output.unlink(missing_ok=True)
    update_row(service, cfg["sheet_id"], sheet_name, row_number, {
        "Reel Status": "GENERATING",
        "Reel Approval": "",
        "Reel Last Error": "",
    })

    review_video_delivered = False
    try:
        print(f"REEL_STAGE start row={row_number} topic={topic!r}")
        brief = make_brief(cfg["gemini_api_key"], os.getenv("GEMINI_MODEL", "gemini-3.6-flash"), topic, post)
        brief["script"] = sanitize_social_copy(brief["script"])
        script_family = _visual_topic_family(brief["script"])
        if topic_family != "general" and script_family not in {"general", topic_family}:
            raise RuntimeError(
                "REEL_SCRIPT_TOPIC_MISMATCH: generated narration does not match the approved post topic "
                f"(topic_family={topic_family}, script_family={script_family}); refusing to render."
            )
        print("REEL_STAGE brief=ok")
        output_dir.mkdir(parents=True, exist_ok=True)
        brief["script"] = prepare_tts_script(brief["script"])
        (output_dir / "script.txt").write_text(brief["script"], encoding="utf-8")
        reel_plan = {
            "topic": topic,
            "source_id": safe_source_id,
            "row_number": row_number,
            "run_id": run_id,
            **brief,
        }
        (output_dir / "reel_plan.json").write_text(json.dumps(reel_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "delivery_map.json").write_text(json.dumps(brief.get("emotion_map", []), ensure_ascii=False, indent=2), encoding="utf-8")

        scene_dir = output_dir / "scenes"
        scene_dir.mkdir(parents=True, exist_ok=True)
        # Each scene illustrates its legal issue; visual QA adds no nationality, culture, era, or cast restriction.
        # Six distinct scene images keep one Reel within the verified free-tier
        # FLUX.2 Dev daily allocation while preserving enough motion beats for Remotion.
        # Every selected scene must pass topic-specific visual QA; no generic placeholders.
        reel_scene_count = 6
        scene_prompts = brief["video_terms"][:reel_scene_count]
        brief["video_terms"] = scene_prompts
        reel_plan["video_terms"] = scene_prompts
        (output_dir / "reel_plan.json").write_text(
            json.dumps(reel_plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        scenes = []
        try:
            from image_generator import create_legal_image
            from image_qa import qa_image
            cloudflare_account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
            cloudflare_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
            for scene_index, scene_prompt in enumerate(scene_prompts, start=1):
                image_path = scene_dir / f"ai_scene_{scene_index:02d}.jpg"
                accepted = False
                active_prompt = str(scene_prompt)
                generation_error = ""
                visual_providers = {1: "cloudflare", 2: "wikimedia", 3: "pixabay"}
                for visual_attempt in range(1, 4):
                    try:
                        create_legal_image(
                            topic=visual_topic,
                            image_brief=active_prompt,
                            visual_description=active_prompt,
                            post_context=post,
                            output_path=str(image_path),
                            api_key=cfg["gemini_api_key"],
                            cloudflare_account_id=cloudflare_account,
                            cloudflare_api_token=cloudflare_token,
                            aspect_ratio="9:16",
                            provider=visual_providers[visual_attempt],
                        )
                        visual_qa = qa_image(
                            api_key=cfg["gemini_api_key"],
                            image_path=str(image_path),
                            topic=visual_topic,
                            image_brief=active_prompt,
                        )
                        if visual_qa.get("decision") == "PASS":
                            accepted = True
                            print(
                                f"REEL_STAGE ai_scene={scene_index}/{reel_scene_count} provider_generated=true "
                                f"legal_relevance=passed attempt={visual_attempt}"
                            )
                            break
                        print(
                            f"REEL_STAGE ai_scene={scene_index}/{reel_scene_count} rejected=visual_qa "
                            f"attempt={visual_attempt} issues={json.dumps(visual_qa.get('issues', []), ensure_ascii=False)}"
                        )
                        regeneration_hint = str(visual_qa.get("regeneration_prompt", "") or "").strip()
                        active_prompt = str(scene_prompt) + (
                            f" VISUAL QA FEEDBACK: {regeneration_hint}" if regeneration_hint else
                            " Make the scene more directly depict the specific legal problem and evidence in the post."
                        )
                    except Exception as scene_generation_exc:
                        generation_error = str(scene_generation_exc)
                        print(
                            f"REEL_STAGE ai_scene={scene_index}/{reel_scene_count} generation_error="
                            f"{generation_error[:700]}"
                        )
                        break

                if not accepted:
                    # Never fill a failed scene with a generic legal placeholder.
                    # A Reel is reviewable only when every scene is independently
                    # generated or sourced for its own approved visual brief.
                    raise RuntimeError(
                        f"REEL_SCENE_VISUAL_QA_FAILED: scene={scene_index}/{reel_scene_count} "
                        f"providers_tried={list(visual_providers.values())} "
                        f"last_generation_error={generation_error[:500]!r}; refusing generic fallback."
                    )
                scenes.append(image_path)
        except Exception as image_exc:
            # Do not silently replace failed topic-specific generations with
            # unrelated catalog stock photos. A missing scene blocks review delivery.
            raise RuntimeError(
                "REEL_STAGE topic_specific_image_generation_failed; refusing off-topic stock fallback: "
                + str(image_exc)
            ) from image_exc
        if len(scenes) != reel_scene_count:
            raise RuntimeError(
                f"REEL_STAGE image_pack_incomplete: expected {reel_scene_count} topic-specific AI scenes, got {len(scenes)}."
            )

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
        # Preserve Commons attribution and license metadata alongside each visual.
        for scene in scenes:
            provenance_file = scene.with_suffix(scene.suffix + ".provenance.json")
            if not provenance_file.exists():
                continue
            provenance = json.loads(provenance_file.read_text(encoding="utf-8"))
            metadata = provenance.get("source_metadata") or {}
            if metadata.get("source") != "Wikimedia Commons":
                continue
            license_name = str(metadata.get("license", ""))
            sources.append({
                "provider": "Wikimedia Commons",
                "title": metadata.get("title", ""),
                "creator": metadata.get("artist", ""),
                "source_url": metadata.get("source_page", ""),
                "media_url": metadata.get("source_url", ""),
                "license": "by" if license_name.upper().startswith("CC BY") else "public-domain",
                "license_name": license_name,
                "license_url": metadata.get("license_url", ""),
            })
        # Avoid duplicate credits if a repeated scene resolved to the same Commons file.
        deduped_sources = []
        seen_source_urls = set()
        for source in sources:
            source_key = str(source.get("source_url") or source.get("media_url") or "")
            if source_key and source_key in seen_source_urls:
                continue
            if source_key:
                seen_source_urls.add(source_key)
            deduped_sources.append(source)
        sources = deduped_sources
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
        try:
            generate_gemini_tts_audio(cfg["gemini_api_key"], brief["script"], brief.get("emotion_map", []), tts_audio)
            print("REEL_STAGE tts=gemini_ok")
        except Exception as gemini_tts_exc:
            print(f"REEL_STAGE tts=gemini_unavailable reason={gemini_tts_exc}")
            tts_audio = output_dir / "voice-google-cloud.wav"
            try:
                generate_google_cloud_arabic_tts_audio(cfg["service_account_info"], brief["script"], tts_audio)
                print("REEL_STAGE tts=google_cloud_ok")
            except Exception as cloud_tts_exc:
                raise RuntimeError(
                    "Gemini TTS failed and Google Cloud TTS fallback failed; refusing Telegram delivery. "
                    f"Gemini={gemini_tts_exc}; Google Cloud={cloud_tts_exc}"
                ) from cloud_tts_exc

        fit_reel_narration_duration(tts_audio, target_seconds=62.0)
        print(f"REEL_STAGE tts_final_duration={_media_duration(tts_audio):.1f}s")

        # The former Python/FFmpeg video builders are retired.
        # Keep the existing image-generation and TTS stages; Remotion alone composes the final MP4.
        slogan_audio = output_dir / "slogan-ask-mahmoud.wav"
        slogan_text = prepare_tts_script("خليك فاكر دايما ... اسأل محمود")
        try:
            generate_gemini_tts_audio_unbounded(
                cfg["gemini_api_key"], slogan_text,
                [{"sentence_index": 1, "delivery_emotion": "confident memorable sign-off"}],
                slogan_audio, min_seconds=1.0, max_seconds=8.0,
            )
            print("REEL_STAGE slogan=gemini_tts_ok")
        except Exception as slogan_gemini_exc:
            print(f"REEL_STAGE slogan=gemini_unavailable reason={slogan_gemini_exc}")
            try:
                generate_google_cloud_short_arabic_tts_audio(
                    cfg["service_account_info"], slogan_text, slogan_audio
                )
                print("REEL_STAGE slogan=google_cloud_tts_ok")
            except Exception as slogan_cloud_exc:
                raise RuntimeError(
                    "REEL_STAGE slogan_generation_failed; refusing delivery: "
                    f"Gemini={slogan_gemini_exc}; Google Cloud={slogan_cloud_exc}"
                ) from slogan_cloud_exc

        video_path = output_dir / "daily-reel.mp4"
        from remotion_renderer import render_reel_with_remotion
        render_reel_with_remotion(
            scenes=scenes,
            voice_audio=tts_audio,
            slogan_audio=slogan_audio,
            logo=Path(os.getenv("BRAND_LOGO_PATH", "لوجو اسال محمود 3دي.png")),
            script=brief["script"],
            output_video=video_path,
        )

        if not video_path.is_file():
            raise RuntimeError("Reel output MP4 is missing.")
        final_duration = _media_duration(video_path)
        if final_duration < float(REEL_MIN_DURATION_SECONDS) or final_duration > float(REEL_MAX_DURATION_SECONDS):
            raise RuntimeError(f"Reel delivery blocked: final duration {final_duration:.1f}s exceeds configured {REEL_MIN_DURATION_SECONDS}–{REEL_MAX_DURATION_SECONDS}s limit.")
        audio_probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(video_path)], capture_output=True, text=True, check=False, timeout=30)
        if not audio_probe.stdout.strip():
            raise RuntimeError("Reel delivery blocked: final MP4 has no audio stream.")
        current_reel_review = str(row.get("Reel Review", "") or "").strip()
        existing_reel_status = str(row.get("Reel Status", "") or "").strip().upper()
        existing_reel_file = str(row.get("Reel File", "") or "").strip()
        force_regenerate = os.getenv("REEL_FORCE_REGENERATE", "").strip().lower() in {"1", "true", "yes", "on"}

        # Persist the reviewable state BEFORE sending Telegram buttons. The
        # callback webhook can be faster than this workflow: publishing REVIEW
        # first prevents a valid approval from being rejected while status is
        # still GENERATING, and prevents a later Sheet write from erasing it.
        video_digest = hashlib.sha256()
        with video_path.open("rb") as video_handle:
            for chunk in iter(lambda: video_handle.read(1024 * 1024), b""):
                video_digest.update(chunk)
        video_sha256 = video_digest.hexdigest()
        forbidden_sha = str(os.getenv("REEL_FORBIDDEN_VIDEO_SHA256", "5512ebc1239786037f4cd73cc4cd52e7108c60dc6174f06c41a8c7b967e109cd")).strip().lower()
        if video_sha256.lower() == forbidden_sha:
            raise RuntimeError("REEL_CONTAMINATED_VIDEO_FINGERPRINT: generated MP4 matches the known contaminated video; refusing Telegram delivery.")
        if len(video_sha256) != 64:
            raise RuntimeError("REEL_VIDEO_FINGERPRINT_FAILED: generated MP4 has no valid SHA-256 digest.")
        reel_plan["video_sha256"] = video_sha256
        (output_dir / "reel_plan.json").write_text(
            json.dumps(reel_plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        review_payload = {
            "Reel Status": "REVIEW",
            "Reel Script": brief["script"],
            "Reel File": str(video_path),
            "Reel Run ID": run_id,
            "Reel Video SHA256": video_sha256,
            "Reel Approval": "",
            "Reel Review": "REVIEW_READY | awaiting Telegram decision",
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
            raise RuntimeError(f"Could not persist Reel review state before Telegram delivery: {last_sheet_error}")

        # Delivery lock: never send a second review copy for the same row.
        if not force_regenerate and not (force_telegram_review or stale_delivery_lock) and current_reel_review.startswith("TELEGRAM_DELIVERED"):
            print(f"Reel row {row_number} already has TELEGRAM_DELIVERED; refusing duplicate send.")
            review_video_delivered = True
        elif not force_regenerate and not (force_telegram_review or stale_delivery_lock) and current_reel_review.startswith("TELEGRAM_SENDING"):
            print(f"Reel row {row_number} is already TELEGRAM_SENDING; refusing duplicate send.")
            review_video_delivered = False
        elif not force_regenerate and not (force_telegram_review or stale_delivery_lock) and existing_reel_status in {"REVIEW", "APPROVED"} and existing_reel_file:
            print(f"Reel row {row_number} is already in {existing_reel_status} with a Reel File; refusing duplicate Telegram delivery.")
            review_video_delivered = True
        else:
            update_row(service, cfg["sheet_id"], sheet_name, row_number, {"Reel Review": f"TELEGRAM_SENDING | run={os.getenv('GITHUB_RUN_ID','')} | duration={final_duration:.1f}s"})
            callback_fingerprint = video_sha256[:16]
            telegram_result = send_video(
                str(video_path),
                caption=f"🎬 Reel للمراجعة — الصف {row_number}\n\nالموضوع: {topic}\nالمدة: {final_duration:.1f} ثانية\nبصمة النسخة: {callback_fingerprint}",
                reply_markup={"inline_keyboard": [[
                    {"text": "✅ اعتماد الريل", "callback_data": f"reel_approve:{row_number}:{callback_fingerprint}"},
                    {"text": "❌ رفض الريل", "callback_data": f"reel_reject:{row_number}:{callback_fingerprint}"},
                ]]},
            )
            message_id = str((telegram_result or {}).get("message_id", ""))
            # Update only the delivery metadata. Never overwrite Reel Approval:
            # the owner may have approved/rejected while sendVideo was in flight.
            update_row(service, cfg["sheet_id"], sheet_name, row_number, {"Reel Review": f"TELEGRAM_DELIVERED | message_id={message_id} | duration={final_duration:.1f}s"})
            review_video_delivered = True

        print("REEL_READY row=" + str(row_number) + " file=" + str(video_path) + f" duration={final_duration:.1f}s telegram=delivered sheet=review")
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
