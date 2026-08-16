import json

from google import genai


SYSTEM_PROMPT = """
أنت المحرر القانوني الرئيسي لمحتوى "اسأل محمود" التابع للمحامي محمود خيرت.

المهمة:
إنتاج محتوى قانوني مصري احترافي، بسيط جدًا على المواطن العادي في مصر،
طبيعي في لغته، ومفيد عمليًا، بدون أي مظهر آلي أو إنشائي مبالغ فيه.

قواعد إلزامية:
1) اكتب بالعربية، واستخدم تعبيرًا مصريًا طبيعيًا عند الحاجة.
2) ممنوع العبارات المحفوظة مثل:
   "في عالمنا اليوم"، "دعونا نتعرف"، "من الجدير بالذكر".
3) لا تستخدم عناوين ونقاط كثيرة بلا داعٍ.
4) اجعل البوست كأنه مكتوب بواسطة محامٍ مصري يشرح مشكلة حقيقية لعميل.
5) ابدأ بموقف أو سؤال واقعي يشد الانتباه.
6) اشرح الحكم القانوني ببساطة ثم ماذا يفعل الشخص عمليًا.
7) لا تستخدم لغة قانونية معقدة إذا كان يمكن شرحها للعامة.
8) ممنوع اختلاق مادة قانونية أو حكم قضائي أو رقم قضية أو تاريخ.
9) إذا أعطيتك مصادر قانونية، التزم بها ولا تضف مصدرًا غير موجود من عندك.
10) إذا كانت نقطة قانونية تحتاج تحققًا من مصدر ولم يوجد المصدر في المدخل،
    لا تخترعها؛ ضعها في review_flags.
11) لا تذكر أنك ذكاء اصطناعي ولا تتحدث عن طريقة توليد النص.
12) تجنب التكرار.
13) اجعل CTA في النهاية طبيعيًا، وليس تسويقيًا بشكل فج.
14) استهدف تقريبًا 180 إلى 320 كلمة إلا إذا كانت طبيعة الموضوع تتطلب أقل.
15) استخدم 2 إلى 4 هاشتاجات فقط عند الحاجة.
16) لا تضع روابط أو مراجع وهمية.

أعد JSON مطابقًا للمخطط المطلوب.
"""


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "post": {
            "type": "string",
            "description": "النص النهائي الجاهز للنشر.",
        },
        "image_brief": {
            "type": "string",
            "description": "وصف بصري مختصر للصورة المناسبة للموضوع.",
        },
        "review_flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "ملاحظات تحتاج مراجعة قبل النشر.",
        },
        "legal_sources_used": {
            "type": "array",
            "items": {"type": "string"},
            "description": "المصادر القانونية التي تم الاعتماد عليها.",
        },
    },
    "required": [
        "post",
        "image_brief",
        "review_flags",
        "legal_sources_used",
    ],
}


def _extract_text(response) -> str:
    text = (getattr(response, "text", None) or "").strip()
    if text:
        return text

    try:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    return str(part_text).strip()
    except Exception:
        pass

    return ""


def generate_post(
    api_key: str,
    model: str,
    topic: str,
    legal_sources: str,
    previous_context: str = "",
) -> dict:
    client = genai.Client(api_key=api_key)

    user_prompt = f"""
الموضوع المطلوب:
{topic}

المصادر القانونية التي يجب الالتزام بها إن وجدت:
{legal_sources or "لا توجد مصادر قانونية مضافة في الشيت."}

سياق سابق اختياري لتجنب التكرار:
{previous_context or "لا يوجد."}

اكتب البوست النهائي الآن.
"""

    response = client.models.generate_content(
        model=model,
        contents=SYSTEM_PROMPT + "\n\n" + user_prompt,
        config={
            "response_format": {
                "text": {
                    "mime_type": "application/json",
                    "schema": OUTPUT_SCHEMA,
                }
            }
        },
    )

    text = _extract_text(response)

    if not text:
        raise RuntimeError("Gemini returned an empty response.")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini returned invalid JSON. "
            f"Raw response: {text[:1500]}"
        ) from exc

    required = (
        "post",
        "image_brief",
        "review_flags",
        "legal_sources_used",
    )

    for key in required:
        if key not in data:
            raise RuntimeError(
                f"Gemini JSON is missing required field: {key}"
            )

    if not isinstance(data["review_flags"], list):
        data["review_flags"] = [str(data["review_flags"])]

    if not isinstance(data["legal_sources_used"], list):
        data["legal_sources_used"] = [str(data["legal_sources_used"])]

    return data
