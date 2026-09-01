from __future__ import annotations

import os
import re
import time
from pathlib import Path

from google import genai


CACHE_DIR = Path(os.getenv("VIDEO_SCRIPT_CACHE_DIR", "video_script_cache"))
GEMINI_MAX_ATTEMPTS = max(1, int(os.getenv("VIDEO_GEMINI_MAX_ATTEMPTS", "2")))
GEMINI_RETRY_DELAY_SECONDS = max(1, int(os.getenv("VIDEO_GEMINI_RETRY_DELAY_SECONDS", "8")))


def _clean(text: str) -> str:
    text = re.sub(r"(?i)\b(?:topic|angle|status|row|post_id)\s*[:=].*?(?=\.|\n|$)", "", text)
    text = re.sub(r"زاوية\s*(?:جديدة|المحتوى)?\s*[:：-]?", "", text)
    text = re.sub(r"اسم\s*الموضوع\s*[:：-]?", "", text)
    return " ".join(text.split()).strip()


def to_egyptian_spoken(text: str) -> str:
    """Conservative offline conversion of formal legal copy into spoken Egyptian Arabic.

    This does not invent legal content or shorten the source. It only changes common
    formal connectors/verb constructions and adds natural spoken punctuation.
    """
    text = _clean(text)
    if not text:
        return ""

    replacements = [
        (r"\bلا يجوز\b", "مينفعش"),
        (r"\bلا يحق\b", "مش من حق"),
        (r"\bيحق له\b", "من حقه"),
        (r"\bيحق لك\b", "من حقك"),
        (r"\bيجب على\b", "لازم"),
        (r"\bيجب أن\b", "لازم"),
        (r"\bيتعين على\b", "لازم"),
        (r"\bيجوز له\b", "ينفع له"),
        (r"\bيجوز لك\b", "ينفع لك"),
        (r"\bيجوز\b", "ينفع"),
        (r"\bيُعتبر\b|\bيعتبر\b", "بيتعتبر"),
        (r"\bيتم\b", "بيتم"),
        (r"\bيكون\b", "بيبقى"),
        (r"\bتكون\b", "بتبقى"),
        (r"\bيمكن\b", "ممكن"),
        (r"\bلا بد من\b", "لازم"),
        (r"\bفي حالة\b", "لو"),
        (r"\bفي حال\b", "لو"),
        (r"\bطبقًا لـ?\b", "حسب"),
        (r"\bوفقًا لـ?\b", "حسب"),
        (r"\bبموجب\b", "حسب"),
        (r"\bبناءً على\b", "على أساس"),
        (r"\bحيث إن\b", "لأن"),
        (r"\bوحيث إن\b", "ولأن"),
        (r"\bوبالتالي\b", "يعني"),
        (r"\bلذلك\b", "وعشان كده"),
        (r"\bوعليه\b", "وعشان كده"),
        (r"\bكما أن\b", "وكمان"),
        (r"\bكذلك\b", "وكمان"),
        (r"\bأيضًا\b|\bأيضا\b", "كمان"),
        (r"\bبالتالي\b", "يعني"),
        (r"\bالذي\b", "اللي"),
        (r"\bالتي\b", "اللي"),
        (r"\bالذين\b", "اللي"),
        (r"\bهذا\b", "ده"),
        (r"\bهذه\b", "دي"),
        (r"\bذلك\b", "ده"),
        (r"\bتلك\b", "دي"),
        (r"\bهنا\b", "هنا"),
        (r"\bأما\b", "أما"),
        (r"\bإذا\b", "لو"),
        (r"\bإن كان\b", "لو كان"),
        (r"\bإن كانت\b", "لو كانت"),
        (r"\bبخصوص\b", "بالنسبة لـ"),
        (r"\bبشأن\b", "بالنسبة لـ"),
        (r"\bيُسمح\b|\bيسمح\b", "ينفع"),
        (r"\bيُمنع\b|\bيمنع\b", "مينفعش"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)

    # Make long written sentences easier for a voice actor/TTS engine to say.
    text = re.sub(r"\s*؛\s*", ". ", text)
    text = re.sub(r"\s*:\s*", ": ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _cache_path(post_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(post_id)).strip("._") or "post"
    return CACHE_DIR / f"{safe}.txt"


def _cached_script(post_id: str) -> str | None:
    path = _cache_path(post_id)
    if not path.is_file():
        return None
    result = _clean(path.read_text(encoding="utf-8"))
    if len(result.split()) < 120:
        return None
    return result


def _is_retryable(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "503",
            "unavailable",
            "429",
            "resource_exhausted",
            "temporarily",
            "timeout",
            "deadline",
            "internal",
        )
    )


def build_script(topic: str, approved_post: str, max_words: int = 180, post_id: str = "") -> str:
    """Create a concise spoken Egyptian-Arabic version of the whole approved post."""
    text = _clean(approved_post)
    if not text:
        raise ValueError("approved_post is required")

    if post_id:
        cached = _cached_script(post_id)
        if cached:
            return " ".join(cached.split()[:max_words]).strip()

    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    client = genai.Client(api_key=key)
    prompt = f"""
أنت كاتب ومقدم محتوى قانوني مصري محترف.
حوّل المنشور القانوني المعتمد أدناه إلى نص يصلح لريل مدته تقريبًا 60 إلى 75 ثانية.

قواعد إلزامية:
- اللهجة مصرية طبيعية ومفهومة، مش فصحى مترجمة ولا لغة كتابية.
- النص يتقال بصوت إنسان مصري: جمل قصيرة، إيقاع طبيعي، وقفات منطقية.
- اختصر المنشور لكن غطّي كل أفكاره القانونية الأساسية، وما تسقطش نقطة جوهرية.
- ممنوع إضافة أي معلومة قانونية أو استنتاج غير موجود في المنشور.
- ممنوع ذكر اسم الموضوع أو الزاوية كبيانات إدارية.
- ممنوع عبارات مثل: "في هذا المنشور" أو "زاوية جديدة".
- ابدأ بخطاف مباشر، ثم الشرح، ثم خلاصة عملية قصيرة.
- من 150 إلى {max_words} كلمة تقريبًا.
- أعد النص فقط بدون عناوين أو علامات اقتباس.

المنشور المعتمد:
{text}
"""

    last_error: Exception | None = None
    for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            result = _clean(getattr(response, "text", ""))
            words = result.split()
            if len(words) < 120:
                raise RuntimeError("Gemini returned a Reel script that is too short.")
            result = " ".join(words[:max_words]).strip()
            if post_id:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                _cache_path(post_id).write_text(result + "\n", encoding="utf-8")
            return result
        except Exception as exc:
            last_error = exc
            message = str(exc)
            if "429" in message or "RESOURCE_EXHAUSTED" in message or "quota" in message.lower():
                raise RuntimeError("GEMINI_QUOTA_EXHAUSTED") from exc
            if attempt >= GEMINI_MAX_ATTEMPTS or not _is_retryable(exc):
                raise
            delay = GEMINI_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
            print(f"Gemini transient failure attempt={attempt}/{GEMINI_MAX_ATTEMPTS}; retrying in {delay}s")
            time.sleep(delay)

    raise RuntimeError("Gemini content generation failed") from last_error
