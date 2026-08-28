from __future__ import annotations

from typing import Any

from google import genai

from gemini_prompts import DEFAULT_TEXT_MODEL, SYSTEM_PROMPT
from gemini_validation import extract_json, normalize_list, normalize_review_level, validate_image_brief


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

    selected_model = (model or DEFAULT_TEXT_MODEL).strip()
    if selected_model.startswith("models/"):
        selected_model = selected_model[len("models/"):]
    if not selected_model:
        selected_model = DEFAULT_TEXT_MODEL

    client = genai.Client(api_key=api_key)
    user_prompt = f"""
الموضوع:
{topic}

المصادر القانونية المتاحة:
{legal_sources or "لا توجد مصادر قانونية مدخلة."}

السياق السابق:
{previous_context or "لا يوجد."}

اكتب البوست النهائي.

ثم أنشئ image_brief لمشهد بصري واحد محدد.

وأخيرًا قيّم مستوى المراجعة القانونية طبقًا للقواعد الموجودة في System Prompt.

مهم جدًا:
لا توقف الموضوع لمجرد أنه حساس.
الهدف هو التمييز بين:
موضوع حساس يمكن شرحه بأمان
وبين ادعاء قانوني دقيق يحتاج تحققًا.

إذا احتجت ذكر عقوبة أو مادة أو رقم أو تاريخ محدد ولا يوجد مصدر موثوق في المدخل:
إما احذف التفصيل من البوست واصغ الفكرة بشكل عام،
أو استخدم BLOCK إذا كان التفصيل جوهريًا ولا يمكن حذفه.

راجع نفسك قبل إخراج JSON.
"""

    try:
        response = client.models.generate_content(
            model=selected_model,
            contents=SYSTEM_PROMPT + "\n\n" + user_prompt,
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini content generation failed: {exc}") from exc

    raw_text = (getattr(response, "text", None) or "").strip()
    if not raw_text:
        raise RuntimeError("Gemini returned an empty response.")

    data = extract_json(raw_text)
    required_fields = ("post", "image_brief", "review_level", "review_flags", "legal_sources_used")
    for field in required_fields:
        if field not in data:
            raise RuntimeError(f"Gemini JSON is missing required field: {field}")

    data["review_level"] = normalize_review_level(data.get("review_level"))
    data["review_flags"] = normalize_list(data.get("review_flags"))
    data["legal_sources_used"] = normalize_list(data.get("legal_sources_used"))
    data["post"] = str(data.get("post", "")).strip()
    data["image_brief"] = str(data.get("image_brief", "")).strip()

    if not data["post"]:
        raise RuntimeError("Gemini returned an empty post.")
    if not data["image_brief"]:
        raise RuntimeError("Gemini returned an empty image_brief.")
    validate_image_brief(data["image_brief"])
    return data
