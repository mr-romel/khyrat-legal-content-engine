from __future__ import annotations

import json
import re
from typing import Any

from google import genai


DEFAULT_TEXT_MODEL = "gemini-3.6-flash"
MAX_GENERATION_ATTEMPTS = 3

SYSTEM_PROMPT = """
أنت رئيس تحرير المحتوى القانوني والمخرج الإبداعي البصري لصفحة «اسأل محمود» التابعة للمحامي محمود خيرت.

اكتب محتوى قانوني مصري احترافي، بسيط، طبيعي، ويبدو مكتوبًا بواسطة محامٍ مصري حقيقي.
- اكتب بالعربية، واستخدم مصرية مهنية طبيعية عند الحاجة.
- ابدأ بموقف أو سؤال واقعي، ثم اشرح القاعدة ببساطة وأثرها العملي.
- لا تختلق مادة أو حكمًا أو رقمًا أو تاريخًا أو عقوبة أو مصدرًا.
- الموضوع الحساس لا يعني BLOCK تلقائيًا؛ إذا كانت التفاصيل الدقيقة غير متحققة احذفها أو عمّمها متى أمكن.
- CTA ناعمة وغير بيعية، تربط بين اختلاف الوقائع والمستندات وبين ضرورة مراجعة الموقف قبل القرار المهم.
- لا تستخدم «احجز استشارة» أو «تواصل معي» أو «كلمني» أو أي صيغة بيع مباشر.
- تجنب العبارات الآلية المحفوظة والتكرار والحشو.

image_brief يجب أن يكون بالإنجليزية فقط، مشهدًا واحدًا محددًا، واقعيًا، سينمائيًا، تحريريًا، مرتبطًا مباشرة بالموضوع، وبدون نص أو شعار أو علامة مائية داخل الصورة.

أعد JSON فقط بهذا الشكل:
{
  "post": "...",
  "image_brief": "...",
  "review_level": "CLEAR|REVIEW|BLOCK",
  "review_flags": [],
  "legal_sources_used": []
}
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"Gemini did not return a valid JSON object. Raw response: {text[:2000]}")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned invalid JSON. Raw response: {text[:2000]}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Gemini JSON response is not an object.")
    return data


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _normalize_review_level(value: Any) -> str:
    level = str(value or "").strip().upper()
    return level if level in {"CLEAR", "REVIEW", "BLOCK"} else "REVIEW"


def _validate_image_brief(image_brief: str) -> None:
    brief = image_brief.strip().lower()
    if not brief:
        raise RuntimeError("Gemini returned an empty image_brief.")
    generic = (
        "professional legal image", "professional law image", "legal background",
        "lawyer at desk", "generic legal image", "generic justice scales",
        "abstract legal background", "legal themed image", "legal concept",
    )
    matched = [phrase for phrase in generic if phrase in brief]
    if matched:
        raise RuntimeError(f"Gemini returned a generic image brief: {matched}")
    markers = (
        "person", "people", "man", "woman", "document", "paper", "room", "office",
        "street", "hands", "expression", "body language", "camera", "lighting",
        "close-up", "medium shot", "background",
    )
    if sum(1 for marker in markers if marker in brief) < 3:
        raise RuntimeError("Gemini image_brief is too generic.")


def _post_quality_ok(post: str) -> bool:
    text = re.sub(r"\s+", " ", str(post or "")).strip()
    words = re.findall(r"\S+", text)
    # This is the pre-editorial generation gate. LinkedIn is produced separately
    # by editorial_review, so this gate must not reject usable source content merely
    # because Gemini chose a different natural CTA wording.
    return len(text) >= 650 and len(words) >= 120


def _soft_cta_present(post: str) -> bool:
    text = str(post or "").casefold()
    markers = (
        "التفاصيل", "الوقائع", "المستند", "مراجعة", "قبل ما تاخد قرار",
        "قبل اتخاذ القرار", "محامٍ", "محامي", "موقفك القانوني", "القرار القانوني",
        "القرار", "الموقف القانوني",
    )
    return any(marker in text for marker in markers)


def _validate_data(data: dict[str, Any]) -> dict[str, Any]:
    for field in ("post", "image_brief", "review_level", "review_flags", "legal_sources_used"):
        if field not in data:
            raise RuntimeError(f"Gemini JSON is missing required field: {field}")
    data["review_level"] = _normalize_review_level(data.get("review_level"))
    data["review_flags"] = _normalize_list(data.get("review_flags"))
    data["legal_sources_used"] = _normalize_list(data.get("legal_sources_used"))
    data["post"] = str(data.get("post", "")).strip()
    data["image_brief"] = str(data.get("image_brief", "")).strip()
    if not data["post"]:
        raise RuntimeError("Gemini returned an empty post.")
    _validate_image_brief(data["image_brief"])
    return data


def _generate_once(client: Any, selected_model: str, prompt: str) -> dict[str, Any]:
    response = client.models.generate_content(
        model=selected_model,
        contents=SYSTEM_PROMPT + "\n\n" + prompt,
    )
    raw_text = (getattr(response, "text", None) or "").strip()
    if not raw_text:
        raise RuntimeError("Gemini returned an empty response.")
    return _validate_data(_extract_json(raw_text))


def generate_post(
    api_key: str,
    model: str,
    topic: str,
    legal_sources: str,
    previous_context: str = "",
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    topic = (topic or "").strip()
    if not topic:
        raise RuntimeError("Topic is empty.")
    selected_model = (model or DEFAULT_TEXT_MODEL).strip().removeprefix("models/") or DEFAULT_TEXT_MODEL
    client = genai.Client(api_key=api_key)

    base_prompt = f"""
الموضوع:
{topic}

المصادر القانونية المتاحة:
{legal_sources or "لا توجد مصادر قانونية مدخلة."}

السياق السابق لتجنب التكرار:
{previous_context or "لا يوجد."}

اكتب مسودة قانونية جاهزة لكي تمر على المراجع القانوني والتحرير النهائي.
استهدف تقريبًا 180 إلى 320 كلمة، لكن لا تحشو النص فقط للوصول إلى رقم.
ابدأ من موقف حقيقي، اشرح الفكرة، وضّح الأثر العملي، وأنهِ بـCTA طبيعية غير بيعية.
إذا لم تكن معلومة دقيقة متحققة، لا تخترعها؛ احذفها أو صغها بصورة عامة وآمنة.
أنشئ أيضًا image_brief مناسبًا للمشهد نفسه.
"""

    retry_prompt = base_prompt + """

مراجعة جودة قبل الإخراج:
تأكد أن المنشور مفيد ومتماسك وليس مختصرًا بشكل مخل، وأن نهايته تتضمن إشارة طبيعية إلى اختلاف الوقائع أو المستندات أو ضرورة مراجعة الموقف قبل القرار المهم.
لا تستخدم صيغة بيع مباشر.
"""

    last_error: Exception | None = None
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        try:
            data = _generate_once(client, selected_model, base_prompt if attempt == 1 else retry_prompt)
            if _post_quality_ok(data["post"]) and _soft_cta_present(data["post"]):
                return data
            if _post_quality_ok(data["post"]):
                data["post"] = data["post"].rstrip() + "\n\nوالتفاصيل والوقائع والمستندات قد تغيّر التقييم القانوني، لذلك مراجعة الموقف قبل اتخاذ قرار مهم قد تكون فارقة."
                if _post_quality_ok(data["post"]):
                    return data
            last_error = RuntimeError("Gemini returned content below the pre-editorial quality threshold.")
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Gemini content generation failed after {MAX_GENERATION_ATTEMPTS} attempts: {last_error}")
