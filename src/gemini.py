from __future__ import annotations

import json
import re
from typing import Any

from google import genai


DEFAULT_TEXT_MODEL = "gemini-3.6-flash"


SYSTEM_PROMPT = """
أنت المحرر القانوني الرئيسي لمحتوى "اسأل محمود"
التابع للمحامي محمود خيرت.

هدفك:
إنتاج محتوى قانوني مصري احترافي، بسيط جدًا على المواطن العادي في مصر،
طبيعي في لغته، مفيد عمليًا، ويبدو كأنه مكتوب بواسطة محامٍ مصري حقيقي.

قواعد المحتوى:

1) اكتب بالعربية.
2) استخدم تعبيرات مصرية طبيعية عند الحاجة بدون مبالغة.
3) ممنوع العبارات الآلية المحفوظة مثل:
   "في عالمنا اليوم"،
   "دعونا نتعرف"،
   "من الجدير بالذكر"،
   "في هذا المقال"،
   "لا شك أن".
4) لا تستخدم عناوين كثيرة أو نقاطًا كثيرة بلا داعٍ.
5) ابدأ بموقف أو سؤال واقعي يشد الانتباه.
6) اشرح القاعدة القانونية بلغة بسيطة ثم وضح ماذا يفعل الشخص عمليًا.
7) لا تستخدم لغة قانونية معقدة إذا كان يمكن شرحها للعامة.
8) ممنوع اختلاق مادة قانونية أو حكم قضائي أو رقم قضية أو تاريخ.
9) إذا أعطيتك مصادر قانونية، التزم بها ولا تضف مصدرًا غير موجود.
10) إذا كانت نقطة قانونية تحتاج تحققًا ولم يوجد لها مصدر في المدخل،
    اذكر "يحتاج مراجعة قانونية" داخل review_flags ولا تخترع المعلومة.
11) لا تذكر أنك ذكاء اصطناعي.
12) تجنب التكرار والجمل النمطية.
13) اجعل CTA طبيعية وغير بيعية.
14) استهدف تقريبًا 180 إلى 320 كلمة، إلا إذا كان الموضوع يحتاج أقل.
15) استخدم 2 إلى 4 هاشتاجات كحد أقصى عند الحاجة.
16) لا تضع روابط أو مراجع وهمية.

قواعد الصورة:

17) image_brief ليس نصًا سيظهر على الصورة.
18) image_brief هو Visual Brief لمولد صور AI.
19) يجب أن يصف مشهدًا بصريًا حقيقيًا وليس Poster أو Infographic.
20) لا تضع أي نص مكتوب داخل الصورة.
21) لا تضع عنوان الموضوع داخل الصورة.
22) لا تضع شرحًا قانونيًا أو فقرات داخل الصورة.
23) لا تستخدم ميزان العدالة بشكل تلقائي.
24) استخدم أشخاصًا وأشياءً ومكانًا وتصرفًا وانفعالات مرتبطة بالمشكلة.
25) عند مناسبة الموضوع، استخدم سياقًا مصريًا واقعيًا.
26) لا تجعل كل الصور مجرد محامٍ يجلس خلف مكتب.
27) الصورة يجب أن تكون مناسبة لمنشور Facebook قانوني احترافي.
28) التركيب Portrait بنسبة 4:5.
29) يجب أن تكون الصورة واقعية وسينمائية واحترافية.
30) image_brief يجب أن يكون باللغة الإنجليزية.
31) لا تذكر في image_brief أي نص مطلوب كتابته داخل الصورة.
32) لا تضف شعارات أو Watermark.
33) اجعل الصورة مفهومة بصريًا حتى بدون قراءة الكابشن.

أعد JSON فقط.
بدون Markdown.
بدون ```json.

الشكل:

{
  "post": "...",
  "image_brief": "...",
  "review_flags": [],
  "legal_sources_used": []
}
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()

    # إزالة Markdown fences إن وجدت.
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    # محاولة مباشرة.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # محاولة استخراج أول JSON object.
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(
            "Gemini did not return a JSON object. "
            f"Raw response: {text[:2000]}"
        )

    candidate = text[start:end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini returned invalid JSON. "
            f"Raw response: {text[:2000]}"
        ) from exc


def generate_post(
    api_key: str,
    model: str,
    topic: str,
    legal_sources: str,
    previous_context: str = "",
) -> dict[str, Any]:

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    selected_model = (
        model or DEFAULT_TEXT_MODEL
    ).strip()

    if selected_model.startswith("models/"):
        selected_model = selected_model[len("models/"):]

    if not selected_model:
        selected_model = DEFAULT_TEXT_MODEL

    client = genai.Client(api_key=api_key)

    user_prompt = f"""
الموضوع:
{topic}

المصادر القانونية المدخلة:
{legal_sources or "لا توجد مصادر قانونية مضافة."}

السياق السابق لتجنب التكرار:
{previous_context or "لا يوجد."}

اكتب المحتوى النهائي.

بعد ذلك أنشئ Visual Brief مستقل للصورة.

فكر بهذه الطريقة:
ما المشهد الذي لو شاهده المواطن قبل قراءة الكابشن
سيفهم المشكلة أو يشعر بها؟

مثال:
موضوع إيصال أمانة:
مشهد واقعي لشخص يسلم مستندًا لشخص آخر في موقف متوتر.

موضوع عقد:
شخص يراجع عقدًا ويكتشف بندًا مقلقًا.

موضوع فصل موظف:
موظف يتلقى قرارًا من جهة العمل.

هذه أمثلة على التفكير فقط.
لا تنسخها حرفيًا.
ابتكر المشهد المناسب للموضوع الحقيقي.

image_brief يجب أن يكون:
- باللغة الإنجليزية
- بصريًا فقط
- واقعيًا
- 4:5 portrait
- بدون أي نص داخل الصورة
- بدون عنوان
- بدون شرح
- بدون شعار
- بدون watermark
"""

    response = client.models.generate_content(
        model=selected_model,
        contents=SYSTEM_PROMPT + "\n\n" + user_prompt,
    )

    raw_text = (
        getattr(response, "text", None) or ""
    ).strip()

    if not raw_text:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    data = _extract_json(raw_text)

    required_fields = (
        "post",
        "image_brief",
        "review_flags",
        "legal_sources_used",
    )

    for field in required_fields:
        if field not in data:
            raise RuntimeError(
                f"Gemini JSON is missing required field: {field}"
            )

    if not isinstance(data["review_flags"], list):
        data["review_flags"] = [
            str(data["review_flags"])
        ]

    if not isinstance(
        data["legal_sources_used"],
        list,
    ):
        data["legal_sources_used"] = [
            str(data["legal_sources_used"])
        ]

    data["post"] = str(
        data["post"]
    ).strip()

    data["image_brief"] = str(
        data["image_brief"]
    ).strip()

    if not data["post"]:
        raise RuntimeError(
            "Gemini returned an empty post."
        )

    if not data["image_brief"]:
        raise RuntimeError(
            "Gemini returned an empty image brief."
        )

    return data
