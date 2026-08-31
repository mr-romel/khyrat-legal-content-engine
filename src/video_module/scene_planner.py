from __future__ import annotations

import json
import os
import re
from typing import Any

from google import genai


SYSTEM = """
أنت مخرج محتوى ريلز قانوني لصفحة محامٍ مصري.
حوّل محتوى المنشور القانوني المعتمد إلى 3 إلى 5 مشاهد بصرية.
المشهد يجب أن يشرح فكرة قانونية من المنشور بصريًا، وليس مجرد صورة لمحامٍ أو محكمة.
استخدم سياقًا مصريًا واقعيًا عند ملاءمته.
لا تضف أي معلومة قانونية غير موجودة في المنشور.
ممنوع استخدام عنوان الموضوع أو الزاوية كبيانات إدارية داخل المشاهد.
ممنوع النصوص والكتابة والشعارات داخل الصور.
أعد JSON فقط بالشكل:
{"scenes":[{"purpose":"...","image_brief":"..."}]}
"""


def _json(text: str) -> dict[str, Any]:
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.I)
    try:
        value = json.loads(clean)
    except json.JSONDecodeError:
        start, end = clean.find("{"), clean.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("Gemini scene planner returned invalid JSON.")
        value = json.loads(clean[start:end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("Gemini scene planner returned a non-object.")
    return value


def plan_scenes(*, post: str, model: str | None = None, api_key: str | None = None, count: int = 4) -> list[dict[str, str]]:
    key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    if not post.strip():
        raise ValueError("approved post is required")
    count = max(3, min(5, count))
    client = genai.Client(api_key=key)
    prompt = f"""
المنشور المعتمد:
{post.strip()}

قسّم الأفكار الواردة في المنشور إلى {count} مشاهد بصرية مترابطة.
كل مشهد لازم يكون مختلفًا بصريًا ويخدم نقطة حقيقية من المنشور.
اكتب image_brief تفصيليًا يكفي لمولد صور فوتوغرافية واقعية.
"""
    response = client.models.generate_content(
        model=(model or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip(),
        contents=SYSTEM + "\n" + prompt,
    )
    data = _json(getattr(response, "text", ""))
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        raise RuntimeError("Gemini scene planner returned no scenes.")
    result: list[dict[str, str]] = []
    for scene in scenes[:5]:
        if not isinstance(scene, dict):
            continue
        brief = str(scene.get("image_brief", "")).strip()
        purpose = str(scene.get("purpose", "")).strip()
        if brief:
            result.append({"purpose": purpose, "image_brief": brief})
    if len(result) < 3:
        raise RuntimeError("Gemini scene planner returned fewer than 3 usable scenes.")
    return result[:count]
