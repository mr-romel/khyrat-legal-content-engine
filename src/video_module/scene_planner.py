from __future__ import annotations

import json
import os
import re
from typing import Any

from google import genai


SYSTEM = """
أنت مخرج محتوى ريلز قانوني لصفحة محامٍ مصري.
حوّل محتوى المنشور القانوني المعتمد إلى 3 إلى 5 مشاهد بصرية.
المشهد يجب أن يشرح فكرة محددة من المنشور بصريًا، وليس مجرد صورة لمحامٍ أو مستندات.
استخدم سياقًا مصريًا واقعيًا عند ملاءمته.
لا تضف أي معلومة قانونية غير موجودة في المنشور.
ممنوع استخدام عنوان الموضوع أو الزاوية كبيانات إدارية داخل المشاهد.
ممنوع النصوص والكتابة والشعارات داخل الصور.

كل image_brief يجب أن يكون وصفًا بصريًا قابلًا للتنفيذ، ويذكر بوضوح:
الشخص/الأشخاص أو العنصر الرئيسي + الفعل الذي يحدث + المكان/السياق + الشيء القانوني المهم + التكوين أو الإحساس البصري.
لا تستخدم أوصافًا عامة مثل: legal documents, legal scene, lawyer, courthouse, paperwork, justice scales وحدها.
لا تكتب image_brief من كلمة أو كلمتين أو عبارة عامة.

أعد JSON فقط بالشكل:
{"scenes":[{"purpose":"...","image_brief":"..."}]}
"""

GENERIC_BRIEFS = {
    "legal documents", "legal document", "documents", "paperwork",
    "legal scene", "lawyer", "law office", "courthouse", "justice scales",
    "legal papers", "legal paperwork", "legal background",
}


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


def _is_generic_brief(brief: str) -> bool:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", brief.lower()).strip()
    if normalized in GENERIC_BRIEFS:
        return True
    if len(normalized.split()) < 8:
        return True
    generic_terms = sum(term in normalized for term in ("legal documents", "legal scene", "paperwork", "lawyer", "courthouse"))
    return generic_terms >= 1 and len(normalized.split()) < 14


def _build_prompt(post: str, count: int, feedback: str = "") -> str:
    retry = f"\n\nتصحيح إلزامي للمحاولة السابقة: {feedback}\n" if feedback else ""
    return f"""
المنشور المعتمد:
{post.strip()}

قسّم الأفكار الواردة في المنشور إلى {count} مشاهد بصرية مترابطة.
كل مشهد لازم يكون مختلفًا بصريًا ويخدم نقطة حقيقية ومحددة من المنشور.
اكتب image_brief تفصيليًا لمولد صور فوتوغرافية واقعية.
كل brief يجب أن يصف مشهدًا يمكن تصويره: من الموجود في الكادر، ماذا يفعل، أين يحدث، وما العنصر المرتبط بالنقطة التي يشرحها المشهد.
لا تكتفِ بعبارات عامة مثل "legal documents" أو "lawyer" أو "courthouse".
لا تضف كتابة أو أرقامًا أو مواد قانونية أو وقائع غير موجودة في المنشور.
{retry}
"""


def plan_scenes(*, post: str, model: str | None = None, api_key: str | None = None, count: int = 4) -> list[dict[str, str]]:
    key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    if not post.strip():
        raise ValueError("approved post is required")
    count = max(3, min(5, count))
    client = genai.Client(api_key=key)
    model_name = (model or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    feedback = ""

    for attempt in range(1, 3):
        response = client.models.generate_content(
            model=model_name,
            contents=SYSTEM + "\n" + _build_prompt(post, count, feedback),
        )
        data = _json(getattr(response, "text", ""))
        scenes = data.get("scenes")
        if not isinstance(scenes, list):
            feedback = "أعد JSON صحيحًا يحتوي على scenes."
            continue

        result: list[dict[str, str]] = []
        generic: list[str] = []
        for scene in scenes[:5]:
            if not isinstance(scene, dict):
                continue
            brief = str(scene.get("image_brief", "")).strip()
            purpose = str(scene.get("purpose", "")).strip()
            if not brief:
                continue
            if _is_generic_brief(brief):
                generic.append(brief)
                continue
            result.append({"purpose": purpose, "image_brief": brief})

        if len(result) >= 3:
            return result[:count]
        feedback = (
            "المشاهد السابقة احتوت أوصافًا عامة غير مقبولة: "
            + repr(generic)
            + ". أعد إنشاء كل المشاهد بوصف محدد للفعل والمكان والعنصر الرئيسي، "
            "واربط كل مشهد بنقطة فعلية من المنشور."
        )

    raise RuntimeError("Gemini scene planner returned only generic or unusable image briefs after retry.")
