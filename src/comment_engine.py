from __future__ import annotations

import json
import re
from typing import Any

from google import genai


SYSTEM_PROMPT = """
أنت محرر تفاعل اجتماعي لصفحة محامٍ مصري.
أنشئ 5 تعليقات مختلفة تمامًا على نفس المنشور.
التعليقات ليست تكرارًا للمنشور وليست حشوًا.
كل تعليق يجب أن يضيف قيمة حقيقية، مثل سؤال ذكي، توضيح عملي، تصحيح تصور شائع، سيناريو قصير، أو دعوة طبيعية للنقاش.
ممنوع ادعاء قانوني رقمي غير موجود في المصادر.
ممنوع ذكر أنك ذكاء اصطناعي.
ممنوع استخدام عبارات من نوع "رائع جدًا" أو "شكرًا لمتابعتكم" كحشو.
أعد JSON فقط بهذا الشكل:
{"facebook_comments":["..."],"linkedin_comments":["..."]}
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*", "", (text or "").strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("Gemini comments response was not valid JSON.")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise RuntimeError("Gemini comments response was not an object.")
    return data


def _normalize(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        key = re.sub(r"\s+", " ", text).casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result[:5]


def generate_comments(
    *,
    api_key: str,
    model: str,
    topic: str,
    post: str,
    legal_sources: str = "",
) -> dict[str, list[str]]:
    client = genai.Client(api_key=api_key)
    prompt = f"""
الموضوع: {topic}

المنشور:
{post}

المصادر القانونية المتاحة:
{legal_sources or 'لا توجد مصادر مدخلة.'}

أنشئ 5 تعليقات Facebook و5 تعليقات LinkedIn.
Facebook: مصري طبيعي، تفاعلي، بسيط.
LinkedIn: مهني، business-oriented، ويضيف قيمة.
اجعل كل تعليق مختلفًا في الوظيفة والأسلوب.
"""
    response = client.models.generate_content(
        model=model,
        contents=[
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT + "\n" + prompt}]}
        ],
    )
    data = _extract_json(getattr(response, "text", ""))
    facebook = _normalize(data.get("facebook_comments"))
    linkedin = _normalize(data.get("linkedin_comments"))
    if len(facebook) < 5 or len(linkedin) < 5:
        raise RuntimeError("Comment engine returned fewer than 5 comments per platform.")
    return {"facebook_comments": facebook, "linkedin_comments": linkedin}
