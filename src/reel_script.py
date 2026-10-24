from __future__ import annotations

import json
import re
from typing import Any

from ai_router import create_client, has_any_provider_key

REEL_SCRIPT_PROMPT = """أنت كاتب ومخرج سيناريوهات ريلز قانونية مصرية قصيرة لصالح «اسأل محمود».
اكتب سيناريو قابلًا للإلقاء أمام الكاميرا باللهجة المصرية الطبيعية، وليس منشورًا مكتوبًا.

البنية الإلزامية بالترتيب، ولا يجوز إسقاط أي جزء:
1) HOOK: جملة قوية جدًا في أول 1–3 ثوانٍ، مرتبطة مباشرة بالموضوع، بلا مقدمة أو تعريف أو تهويل.
2) PROBLEM: موقف ملموس أو خطأ شائع يوضح المشكلة ولماذا تهم المشاهد.
3) SOLUTION: الحل أو الخطوات العملية بوضوح ودقة قانونية، اعتمادًا فقط على الموضوع والمصادر المعطاة. لا تخترع مواد أو مواعيد أو عقوبات أو نتائج مضمونة.
4) CTA: دعوة واحدة قصيرة ومناسبة للتفاعل (تعليق أو مشاركة أو متابعة)، لا تجمع عدة طلبات.
5) END_SLOGAN: سلوجن النهاية الثابت حرفيًا: «اسأل محمود.. اعرف حقك وخد خطوتك صح».

ضوابط الجودة:
- استهدف 25–45 ثانية عند الإلقاء، ما لم يحدد المستخدم مدة أخرى.
- اجعل الجمل قصيرة ومسموعة، وكل جزء يؤدي وظيفة مختلفة.
- لا تكتب تعليمات تصوير مطولة أو مقدمة من نوع «أهلًا بكم».
- لا تكرر الهوك داخل المشكلة، ولا تجعل الحل كلامًا عامًا مثل «استشر محاميًا» فقط.
- لا تضف إخلاء مسؤولية طويلًا داخل السيناريو.
- إذا كانت المصادر غير كافية لحسم نقطة قانونية، صغها بتحفظ ولا تقدمها كقاعدة قطعية.
- أخرج JSON صالحًا فقط بالمفاتيح: hook, problem, solution, cta, end_slogan, full_script, estimated_seconds.
- full_script يجمع الأجزاء بالترتيب وبلا تسميات إنجليزية داخل النص المنطوق.
"""

FIXED_SLOGAN = "اسأل محمود.. اعرف حقك وخد خطوتك صح"


def _extract_json(raw: str) -> dict[str, Any]:
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", str(raw or "").strip(), flags=re.I)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Reel script model response is not valid JSON.")
        data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("Reel script response must be a JSON object.")
    return data


def validate_reel_script(data: dict[str, Any]) -> dict[str, Any]:
    required = ("hook", "problem", "solution", "cta", "end_slogan", "full_script")
    for key in required:
        if not str(data.get(key) or "").strip():
            raise ValueError(f"Reel script is missing required section: {key}")
    data["end_slogan"] = FIXED_SLOGAN
    sections = [str(data[k]).strip() for k in ("hook", "problem", "solution", "cta")]
    data["full_script"] = "\n\n".join([*sections, FIXED_SLOGAN])
    try:
        seconds = int(data.get("estimated_seconds", 35))
    except (TypeError, ValueError):
        seconds = 35
    data["estimated_seconds"] = max(20, min(seconds, 60))
    return data


def generate_reel_script(
    *,
    api_key: str,
    model: str,
    topic: str,
    legal_sources: str = "",
    source_post: str = "",
    target_seconds: int = 35,
) -> dict[str, Any]:
    """Generate a reel script with mandatory hook/problem/solution/CTA/slogan sections."""
    if not api_key and not has_any_provider_key():
        raise RuntimeError("No text AI provider is configured.")
    topic = str(topic or "").strip()
    if not topic:
        raise ValueError("Reel topic is empty.")

    client = create_client(api_key=api_key, task="text")
    selected_model = str(model or "gemini-3.6-flash").strip().removeprefix("models/")
    prompt = f"""{REEL_SCRIPT_PROMPT}

الموضوع: {topic}
المدة المستهدفة بالثواني: {max(20, min(int(target_seconds), 60))}
نص المنشور أو المادة الأصلية (إن وجدت):
{source_post or "غير متاح"}

المصادر/الملاحظات القانونية المتحققة:
{legal_sources or "لا توجد مصادر مرفقة؛ تجنب التفاصيل القانونية الرقمية أو القطعية غير المتحققة."}

أنشئ السيناريو الآن. اجعل الحل محددًا بقدر ما تسمح به المعلومات، والتزم بسلوجن النهاية حرفيًا.
"""
    response = client.models.generate_content(
        model=selected_model,
        contents=prompt,
        config={"response_mime_type": "application/json", "temperature": 0.35},
    )
    raw = str(getattr(response, "text", "") or "").strip()
    result = validate_reel_script(_extract_json(raw))
    if result["end_slogan"] != FIXED_SLOGAN:
        raise ValueError("Fixed reel slogan validation failed.")
    return result
