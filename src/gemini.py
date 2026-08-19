from __future__ import annotations

import json
import re
from typing import Any

from google import genai


DEFAULT_TEXT_MODEL = "gemini-3.6-flash"


SYSTEM_PROMPT = """
أنت رئيس تحرير المحتوى القانوني والمخرج الإبداعي البصري
لصفحة "اسأل محمود" التابعة للمحامي محمود خيرت.

مهمتك إنتاج:
1) بوست قانوني مصري جاهز للنشر.
2) Visual Brief دقيق لصورة AI.
3) تقييم واضح لمدى الحاجة إلى المراجعة القانونية قبل النشر.

============================================================
أولاً: قواعد المحتوى القانوني
============================================================

1) اكتب بالعربية.
2) استخدم لغة مصرية طبيعية عند الحاجة، بدون افتعال.
3) اجعل الأسلوب بشريًا ومهنيًا ويشبه محاميًا مصريًا حقيقيًا.
4) ممنوع العبارات النمطية مثل:
   "في عالمنا اليوم"
   "دعونا نتعرف"
   "من الجدير بالذكر"
   "في هذا المقال"
   "لا شك أن"
5) لا تكثر من العناوين أو النقاط.
6) ابدأ بموقف أو سؤال واقعي.
7) اشرح القاعدة القانونية ببساطة.
8) وضح الأثر العملي وما الذي يمكن للشخص فعله.
9) لا تختلق أي مادة أو حكم أو رقم أو تاريخ أو عقوبة.
10) لا تدّعِ وجود مصدر لم يتم تقديمه.
11) لا تذكر أنك ذكاء اصطناعي.
12) CTA طبيعية وغير بيعية.
13) 180 إلى 320 كلمة تقريبًا عند الحاجة.
14) 2 إلى 4 هاشتاجات عند الحاجة.
15) لا تستخدم روابط وهمية.

============================================================
ثانياً: قاعدة المراجعة القانونية الجديدة
============================================================

لا تعتبر الموضوع حساسًا وحده سببًا لإيقاف النشر.

الجريمة أو التحرش أو الأسرة أو العمل أو العقود أو الميراث
وغيرها من الموضوعات الحساسة يمكن إنتاج محتوى عنها تلقائيًا
طالما أن الكلام عام ولا يتطلب ادعاء قانونيًا دقيقًا غير متحقق.

استخدم مستويات المراجعة التالية:

CLEAR:
الموضوع يمكن شرحه بشكل عام دون ادعاءات قانونية دقيقة غير متحققة.

REVIEW:
الموضوع يحتاج انتباهًا قانونيًا أو قد يستفيد من مراجعة،
لكن يمكن إنتاجه ونشره طالما لا يحتوي على ادعاء رقمي أو قانوني
دقيق غير متحقق.

BLOCK:
لا تنشر تلقائيًا إذا كان المحتوى يتطلب معلومة دقيقة لا يمكن
التحقق منها من المصادر المدخلة، مثل:
- رقم مادة قانونية محددة وغير متحققة.
- نص مادة قانونية.
- عقوبة أو غرامة أو مدة حبس محددة غير متحققة.
- رقم حكم أو قضية.
- تاريخ تعديل قانوني.
- قانون أو قرار حديث غير موجود في المصادر.
- معلومة رقمية يمكن أن تغير النتيجة القانونية.
- ادعاء قانوني حاسم لا يمكن صياغته بأمان من المعطيات المتاحة.

مهم:
غياب المصادر القانونية لا يعني تلقائيًا BLOCK.

مثال:
موضوع:
"هل إيصال الأمانة يضمن استرداد الفلوس؟"

يمكن مناقشة الفكرة العامة بصورة تعليمية دون اختراع مادة
أو عقوبة أو حكم محدد.

مثال:
"ما عقوبة جريمة التحرش طبقًا للمادة X؟"

لو لم يوجد مصدر يثبت المادة والعقوبة:
BLOCK.

مثال:
"هل التحرش جريمة؟ وما حقوق الشخص المتضرر؟"

يمكن أن يكون CLEAR أو REVIEW إذا أمكن صياغته بصورة عامة
دون اختلاق تفاصيل غير متحققة.

============================================================
ثالثاً: المراجعة الذاتية
============================================================

قبل إخراج JSON:

1) هل أضفت رقم مادة أو عقوبة أو مدة أو تاريخ؟
2) هل هذه المعلومة موجودة في المصادر المدخلة؟
3) هل يمكن حذف الرقم أو صياغة الفكرة بشكل عام وآمن؟
4) هل الموضوع حساس فقط، أم أن هناك ادعاء قانوني دقيق؟
5) لا تستخدم BLOCK لمجرد أن الموضوع حساس.

إذا كان هناك ادعاء دقيق غير متحقق ولا يمكن حذفه:
review_level = "BLOCK"

إذا كان الموضوع يحتاج انتباهًا لكن لا يوجد خطر قانوني مباشر:
review_level = "REVIEW"

خلاف ذلك:
review_level = "CLEAR"

============================================================
رابعاً: الصورة
============================================================

image_brief ليس عنوانًا ولا شرحًا للمقال.

يجب أن يكون:
- English only
- مشهدًا واحدًا محددًا
- 80 إلى 180 كلمة تقريبًا
- مناسبًا لـFLUX
- واقعيًا
- Cinematic
- Editorial
- مرتبطًا مباشرة بالمشكلة
- بدون أي نص داخل الصورة

حدد:
- الأشخاص
- الفعل
- المستند أو العنصر الرئيسي
- المكان
- المشاعر
- الكاميرا
- الإضاءة
- التفاصيل المصرية المناسبة

ممنوع:
- generic legal image
- lawyer at desk
- generic justice scales
- abstract legal background
- poster
- infographic
- text
- logo
- watermark

============================================================
خامساً: الإخراج
============================================================

أعد JSON فقط.

الشكل:

{
  "post": "...",
  "image_brief": "...",
  "review_level": "CLEAR",
  "review_flags": [],
  "legal_sources_used": []
}

القيم المسموح بها لـreview_level فقط:
CLEAR
REVIEW
BLOCK

review_flags يجب أن تحتوي أسبابًا مختصرة وواضحة إذا كان هناك
سبب للمراجعة.

لا تجعل review_flags سببًا للإيقاف إلا عندما يكون
review_level = BLOCK.
"""


def _extract_json(
    text: str,
) -> dict[str, Any]:
    text = (text or "").strip()

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

    try:
        data = json.loads(text)

        if isinstance(data, dict):
            return data

    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if (
        start == -1
        or end == -1
        or end <= start
    ):
        raise RuntimeError(
            "Gemini did not return a valid JSON object. "
            f"Raw response: {text[:2000]}"
        )

    candidate = text[start:end + 1]

    try:
        data = json.loads(candidate)

        if not isinstance(data, dict):
            raise RuntimeError(
                "Gemini JSON response is not an object."
            )

        return data

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini returned invalid JSON. "
            f"Raw response: {text[:2000]}"
        ) from exc


def _normalize_list(
    value: Any,
) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    value = str(value).strip()

    if not value:
        return []

    return [value]


def _normalize_review_level(
    value: Any,
) -> str:
    level = (
        str(value or "")
        .strip()
        .upper()
    )

    if level not in {
        "CLEAR",
        "REVIEW",
        "BLOCK",
    }:
        return "REVIEW"

    return level


def _validate_image_brief(
    image_brief: str,
) -> None:
    brief = (
        image_brief
        .strip()
        .lower()
    )

    if not brief:
        raise RuntimeError(
            "Gemini returned an empty image_brief."
        )

    generic_phrases = [
        "professional legal image",
        "professional law image",
        "legal background",
        "lawyer in office",
        "lawyer at desk",
        "justice scales",
        "legal documents",
        "legal themed image",
        "legal concept",
        "professional legal scene",
    ]

    matched = [
        phrase
        for phrase in generic_phrases
        if phrase in brief
    ]

    if matched:
        raise RuntimeError(
            "Gemini returned a generic image brief: "
            f"{matched}"
        )

    detail_markers = [
        "person",
        "people",
        "man",
        "woman",
        "document",
        "paper",
        "room",
        "office",
        "street",
        "hands",
        "expression",
        "body language",
        "camera",
        "lighting",
        "close-up",
        "medium shot",
        "background",
    ]

    detail_count = sum(
        1
        for marker in detail_markers
        if marker in brief
    )

    if detail_count < 3:
        raise RuntimeError(
            "Gemini image_brief is too generic."
        )


def generate_post(
    api_key: str,
    model: str,
    topic: str,
    legal_sources: str,
    previous_context: str = "",
) -> dict[str, Any]:

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing."
        )

    topic = (
        topic or ""
    ).strip()

    if not topic:
        raise RuntimeError(
            "Topic is empty."
        )

    selected_model = (
        model or DEFAULT_TEXT_MODEL
    ).strip()

    if selected_model.startswith(
        "models/"
    ):
        selected_model = selected_model[
            len("models/"):
        ]

    if not selected_model:
        selected_model = DEFAULT_TEXT_MODEL

    client = genai.Client(
        api_key=api_key
    )

    user_prompt = f"""
الموضوع:
{topic}

المصادر القانونية المتاحة:
{legal_sources or "لا توجد مصادر قانونية مدخلة."}

السياق السابق:
{previous_context or "لا يوجد."}

اكتب البوست النهائي.

ثم أنشئ image_brief لمشهد بصري واحد محدد.

وأخيرًا قيّم مستوى المراجعة القانونية طبقًا للقواعد
الموجودة في System Prompt.

مهم جدًا:
لا توقف الموضوع لمجرد أنه حساس.
الهدف هو التمييز بين:
موضوع حساس يمكن شرحه بأمان
وبين ادعاء قانوني دقيق يحتاج تحققًا.

إذا احتجت ذكر عقوبة أو مادة أو رقم أو تاريخ محدد
ولا يوجد مصدر موثوق في المدخل:
إما احذف التفصيل من البوست واصغ الفكرة بشكل عام،
أو استخدم BLOCK إذا كان التفصيل جوهريًا ولا يمكن حذفه.

راجع نفسك قبل إخراج JSON.
"""

    try:
        response = client.models.generate_content(
            model=selected_model,
            contents=(
                SYSTEM_PROMPT
                + "\n\n"
                + user_prompt
            ),
        )

    except Exception as exc:
        raise RuntimeError(
            f"Gemini content generation failed: {exc}"
        ) from exc

    raw_text = (
        getattr(
            response,
            "text",
            None,
        )
        or ""
    ).strip()

    if not raw_text:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    data = _extract_json(
        raw_text
    )

    required_fields = (
        "post",
        "image_brief",
        "review_level",
        "review_flags",
        "legal_sources_used",
    )

    for field in required_fields:
        if field not in data:
            raise RuntimeError(
                f"Gemini JSON is missing required field: "
                f"{field}"
            )

    data["review_level"] = (
        _normalize_review_level(
            data.get("review_level")
        )
    )

    data["review_flags"] = (
        _normalize_list(
            data.get("review_flags")
        )
    )

    data["legal_sources_used"] = (
        _normalize_list(
            data.get(
                "legal_sources_used"
            )
        )
    )

    data["post"] = (
        str(
            data.get(
                "post",
                "",
            )
        )
        .strip()
    )

    data["image_brief"] = (
        str(
            data.get(
                "image_brief",
                "",
            )
        )
        .strip()
    )

    if not data["post"]:
        raise RuntimeError(
            "Gemini returned an empty post."
        )

    if not data["image_brief"]:
        raise RuntimeError(
            "Gemini returned an empty image_brief."
        )

    _validate_image_brief(
        data["image_brief"]
    )

    return data
