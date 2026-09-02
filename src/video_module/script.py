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
    """Convert common formal legal constructions into understandable Egyptian speech."""
    text = _clean(text)
    if not text:
        return ""
    replacements = [
        (r"\bلا يجوز\b", "مينفعش"), (r"\bلا يحق\b", "مش من حق"),
        (r"\bيحق له\b", "من حقه"), (r"\bيحق لك\b", "من حقك"),
        (r"\bيجب على\b|\bيجب أن\b|\bيتعين على\b", "لازم"),
        (r"\bيجوز له\b", "ينفع له"), (r"\bيجوز لك\b", "ينفع لك"),
        (r"\bيجوز\b", "ينفع"), (r"\bيُعتبر\b|\bيعتبر\b", "بيتعتبر"),
        (r"\bيتم\b", "بيتم"), (r"\bيكون\b", "بيبقى"), (r"\bتكون\b", "بتبقى"),
        (r"\bيمكن\b", "ممكن"), (r"\bلا بد من\b", "لازم"),
        (r"\bفي حالة\b|\bفي حال\b", "لو"),
        (r"\bطبقًا لـ?\b|\bوفقًا لـ?\b|\bبموجب\b", "حسب"),
        (r"\bبناءً على\b", "على أساس"), (r"\bحيث إن\b", "لأن"),
        (r"\bوحيث إن\b", "ولأن"), (r"\bوبالتالي\b|\bبالتالي\b", "يعني"),
        (r"\bلذلك\b|\bوعليه\b", "وعشان كده"), (r"\bكما أن\b|\bكذلك\b", "وكمان"),
        (r"\bأيضًا\b|\bأيضا\b", "كمان"), (r"\bالذي\b|\bالتي\b|\bالذين\b", "اللي"),
        (r"\bهذا\b|\bذلك\b", "ده"), (r"\bهذه\b|\bتلك\b", "دي"),
        (r"\bإذا\b", "لو"), (r"\bإن كان\b", "لو كان"), (r"\bإن كانت\b", "لو كانت"),
        (r"\bبخصوص\b|\bبشأن\b", "بالنسبة لـ"),
        (r"\bيُسمح\b|\bيسمح\b", "ينفع"), (r"\bيُمنع\b|\bيمنع\b", "مينفعش"),
        (r"\bيتوجب\b", "لازم"), (r"\bيلزم\b", "لازم"),
        (r"\bينبغي\b", "الأفضل"), (r"\bوفقًا لما\b", "حسب اللي"),
        (r"\bبصفة عامة\b", "بشكل عام"), (r"\bفيما يتعلق بـ\b", "بالنسبة لـ"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\s*؛\s*", ". ", text)
    text = re.sub(r"\s*:\s*", ": ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\.{2,}", ".", text)
    return re.sub(r"\s+", " ", text).strip()


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
    return any(marker in message for marker in ("503", "unavailable", "429", "resource_exhausted", "temporarily", "timeout", "deadline", "internal"))


def _looks_formal(text: str) -> bool:
    markers = ("بموجب", "طبقًا", "وفقًا", "حيث إن", "وعليه", "يتعين", "يترتب على", "بالتالي", "لا يجوز", "يجب على", "يحق له")
    return sum(1 for marker in markers if marker in text) >= 2


def build_pilot_script(topic: str, approved_post: str, post_id: str = "") -> str:
    """Generate a spoken Egyptian-Arabic script; never truncate the generated result."""
    text = _clean(approved_post)
    if not text:
        raise ValueError("approved_post is required")
    if post_id:
        cached = _cached_script(post_id)
        if cached and not _looks_formal(cached):
            return cached

    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    client = genai.Client(api_key=key)
    prompt = f"""
إنت محامي مصري بيتكلم قدام الكاميرا. حوّل المحتوى القانوني المعتمد تحت لنص فيديو كامل باللهجة المصرية العامية الطبيعية.
المطلوب مش ترجمة للفصحى ومش تبسيط لغوي شكلي؛ المطلوب كلام مصري يتقال فعلًا بصوت محامي شاب واثق من معلوماته.

قواعد إلزامية:
- استخدم العامية المصرية في تركيب الجملة والكلمات: "بص، لو، عشان، كده، ده، دي، اللي، مينفعش، ينفع، من حقك، لازم، ممكن، يعني" عند ملاءمتها.
- ممنوع الفصحى الصحفية أو أسلوب البيانات القانونية مثل "وفقًا" و"بموجب" و"وعليه" و"يتعين" و"يترتب" إلا لو جزء لا يمكن تغييره من اسم قانون أو نص مادة.
- استخدم "إنت/إنتي" أو "حضرتك" حسب السياق، وبأسلوب محامي مصري بيشرح لعميل، مش مدرس بيقرأ كتاب.
- الجمل قصيرة، فيها وقفات طبيعية، ومن غير تراكيب طويلة متداخلة.
- حافظ على كل النقاط القانونية الجوهرية الموجودة في المنشور. ممنوع اختراع حكم أو معلومة أو مثال قانوني غير موجود.
- ابدأ بخطاف طبيعي، وبعده الشرح، وفي النهاية خلاصة عملية واضحة.
- اكتب النص المنطوق فقط، من غير عنوان أو ملاحظات إنتاج.
- استهدف تقريبًا 150 إلى 210 كلمة، لكن لا تحذف فكرة جوهرية فقط للوصول لعدد الكلمات.
- مهم جدًا: راجع النص قبل إرجاعه وتأكد إنه لو اتقري بصوت مصري مش هيبان فصحى.

الموضوع: {topic}

المنشور المعتمد:
{text}
"""
    last_error: Exception | None = None
    for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            result = to_egyptian_spoken(getattr(response, "text", ""))
            if len(result.split()) < 120:
                raise RuntimeError("Gemini returned a Reel script that is too short.")
            if _looks_formal(result):
                raise RuntimeError("Gemini returned overly formal Arabic for the Egyptian pilot.")
            if post_id:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                _cache_path(post_id).write_text(result + "\n", encoding="utf-8")
            print(f"PILOT_SCRIPT_WORDS={len(result.split())}")
            print("PILOT_SCRIPT_DIALECT=Egyptian_colloquial")
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


def build_script(topic: str, approved_post: str, max_words: int = 180, post_id: str = "") -> str:
    """Normal production script path; preserved separately from the isolated pilot."""
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
- اللهجة مصرية طبيعية ومفهومة، مش فصحى مترجمة ولا لغة كتابية.
- جمل قصيرة وإيقاع طبيعي.
- اختصر المنشور لكن غطّي كل أفكاره القانونية الأساسية.
- ممنوع إضافة معلومة قانونية غير موجودة.
- ابدأ بخطاف مباشر ثم الشرح ثم خلاصة عملية.
- من 150 إلى {max_words} كلمة تقريبًا.
- أعد النص فقط.

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
