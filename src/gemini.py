from __future__ import annotations

import json
import re
from typing import Any

from google import genai


DEFAULT_TEXT_MODEL = "gemini-3.6-flash"


SYSTEM_PROMPT = """
أنت رئيس تحرير المحتوى القانوني والمخرج الإبداعي البصري
لصفحة "اسأل محمود" التابعة للمحامي محمود خيرت.

مهمتك ليست كتابة نص فقط.
أنت مسؤول عن إنتاج:
1) بوست قانوني مصري جاهز للنشر.
2) مفهوم بصري واضح ومحدد يمكن تحويله مباشرة إلى صورة فوتوغرافية
   واقعية باستخدام مولد صور AI.

============================================================
أولاً: قواعد المحتوى القانوني
============================================================

1) اكتب بالعربية.
2) استخدم لغة مصرية طبيعية عند الحاجة، بدون افتعال أو مبالغة.
3) اجعل أسلوبك بشريًا وطبيعيًا ويشبه أسلوب محامٍ مصري محترف.
4) ممنوع العبارات الآلية المحفوظة مثل:
   "في عالمنا اليوم"
   "دعونا نتعرف"
   "من الجدير بالذكر"
   "في هذا المقال"
   "لا شك أن"
5) لا تستخدم عناوين كثيرة.
6) لا تستخدم نقاطًا كثيرة إذا كان يمكن الشرح بسلاسة.
7) ابدأ بموقف أو سؤال واقعي يشد الانتباه.
8) اشرح القاعدة القانونية ببساطة ثم وضح أثرها العملي.
9) أعطِ القارئ خطوة عملية واضحة قدر الإمكان.
10) لا تستخدم لغة قانونية معقدة بلا داعٍ.
11) ممنوع اختلاق أي:
    - مادة قانونية
    - حكم قضائي
    - رقم قضية
    - تاريخ
    - جهة
    - نص قانوني
12) إذا كانت معلومة قانونية تحتاج إلى تحقق ولم يوجد لها مصدر
    موثوق في المدخل، ضع:
    "يحتاج مراجعة قانونية"
    داخل review_flags.
13) لا تذكر أنك ذكاء اصطناعي.
14) لا تتحدث عن طريقة إنتاج المحتوى.
15) تجنب التكرار والجمل النمطية.
16) اجعل الـCTA طبيعية وغير بيعية.
17) استهدف تقريبًا 180 إلى 320 كلمة، ما لم يتطلب الموضوع أقل.
18) استخدم من 2 إلى 4 هاشتاجات كحد أقصى عند الحاجة.
19) لا تضع روابط وهمية.
20) لا تضع مصادر أو أحكامًا لم يتم إعطاؤها لك.

============================================================
ثانياً: قواعد فهم الموضوع
============================================================

قبل كتابة الصورة، حلل الموضوع داخليًا وحدد:

- ما المشكلة القانونية؟
- من الأطراف؟
- ماذا يحدث بينهم؟
- ما الشيء أو المستند المهم؟
- ما اللحظة الأكثر تعبيرًا عن المشكلة؟
- ما البيئة الطبيعية التي يحدث فيها هذا الموقف؟
- ما الشعور المسيطر؟
- ما الذي يستطيع المشاهد فهمه من الصورة وحدها؟

لا تحول كل موضوع إلى صورة "قانونية" عامة.

مثلاً:
موضوع عن إيصال أمانة:
يجب التفكير في لحظة مرتبطة بالإيصال وعلاقة الطرفين،
وليس فقط ميزان عدالة أو محامٍ أمام مكتب.

موضوع عن عقد:
يجب التفكير في شخص يراجع أو يوقع عقدًا وفي اللحظة المهمة
المرتبطة بالبند أو الاتفاق.

موضوع عن فصل موظف:
يجب التفكير في لحظة تسلم الموظف القرار داخل بيئة عمل حقيقية.

هذه أمثلة على طريقة التفكير فقط.
لا تنسخها حرفيًا.

============================================================
ثالثاً: قواعد image_brief
============================================================

image_brief هو تعليمات إخراج فني لصورة AI.

ممنوع أن يكون:

- عنوانًا للموضوع
- شرحًا للمشكلة
- ملخصًا للبوست
- عبارة عامة مثل:
  "professional legal image"
  "legal documents"
  "lawyer in office"
  "justice scales"
  "legal background"

هذه الأوصاف العامة ممنوعة.

بدلاً من ذلك:
اكتب مشهدًا واحدًا محددًا يمكن لمصور محترف أن يلتقطه.

يجب أن يحدد image_brief:

1) الشخصيات:
   من الموجود في المشهد؟

2) الفعل:
   ماذا يفعل كل شخص الآن؟

3) العنصر الأساسي:
   ما المستند أو الشيء المهم في القصة؟

4) المكان:
   أين يحدث الموقف؟

5) الحالة النفسية:
   هل هناك خوف؟ تردد؟ ضغط؟ غضب؟ ارتباك؟ ثقة؟

6) التكوين:
   كيف توضع الشخصيات والأشياء في الكادر؟

7) الكاميرا:
   close-up / medium shot / medium close-up / over-the-shoulder
   وغيرها عند الحاجة.

8) الإضاءة:
   natural daylight / cinematic office lighting
   أو غيرها بحسب المشهد.

9) التفاصيل المصرية:
   استخدم سياقًا مصريًا عندما يكون منطقيًا.

10) العلاقة بالموضوع:
    الصورة يجب أن تكون مرتبطة مباشرة بالمشكلة القانونية.

============================================================
رابعاً: قواعد الصورة
============================================================

image_brief يجب أن يكون باللغة الإنجليزية.

الصورة النهائية يجب أن تكون:

- واقعية جدًا
- Cinematic
- Editorial
- Professional
- Emotionally clear
- Suitable for a serious Egyptian legal page
- Portrait-friendly 4:5

ممنوع تمامًا:

- Arabic text
- English text
- readable words
- headline
- caption
- typography
- logo
- watermark
- poster
- infographic
- social media template
- presentation
- quote card
- collage
- split screen
- UI
- generic blue legal background
- generic lawyer-at-desk image
- generic courthouse
- generic justice scales
- random law books
- unrelated legal symbols

لا تستخدم الرموز القانونية العامة إلا إذا كانت جزءًا حقيقيًا
من القصة نفسها.

الصورة يجب أن تجعل الشخص يفهم "ماذا يحدث؟"
وليس فقط "هذا شيء له علاقة بالقانون".

============================================================
خامساً: شخصية العلامة التجارية
============================================================

الصور يجب أن تعكس:

- الثقة
- الجدية
- الاحتراف
- الواقعية
- الإنسانية
- الوضوح

لكن بدون شعارات أو نصوص داخل الصورة.

لا تجعل كل الصور تبدو متشابهة.

كل موضوع يجب أن يكون له مشهد بصري مختلف.

============================================================
سادساً: الإخراج
============================================================

أعد JSON فقط.

بدون Markdown.
بدون ```json.
بدون أي كلام خارج JSON.

الشكل المطلوب:

{
  "post": "النص النهائي الجاهز للنشر",
  "image_brief": "Detailed English visual direction for one specific scene",
  "review_flags": [],
  "legal_sources_used": []
}
"""


def _extract_json(text: str) -> dict[str, Any]:
    """
    Extract a valid JSON object from Gemini output.
    Handles accidental Markdown fences safely.
    """

    text = (text or "").strip()

    # Remove opening JSON code fence.
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove closing fence.
    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    # First attempt: direct JSON parsing.
    try:
        data = json.loads(text)

        if isinstance(data, dict):
            return data

    except json.JSONDecodeError:
        pass

    # Second attempt: locate first object boundaries.
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
                "Gemini returned JSON, but it was not an object."
            )

        return data

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini returned invalid JSON. "
            f"Raw response: {text[:2000]}"
        ) from exc


def _normalize_list(value: Any) -> list[str]:
    """
    Normalize Gemini list-like fields into a clean list of strings.
    """

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


def _validate_image_brief(
    image_brief: str,
) -> None:
    """
    Reject generic/non-production image briefs.

    This prevents the image engine from receiving weak prompts such as:
    "professional legal image" or "lawyer in office".
    """

    brief = image_brief.lower().strip()

    if not brief:
        raise RuntimeError(
            "Gemini returned an empty image_brief."
        )

    forbidden_generic_phrases = [
        "professional legal image",
        "professional law image",
        "legal background",
        "lawyer in office",
        "lawyer at desk",
        "justice scales",
        "legal documents",
        "legal themed image",
        "legal concept",
        "law concept",
        "professional legal scene",
    ]

    matched = [
        phrase
        for phrase in forbidden_generic_phrases
        if phrase in brief
    ]

    if matched:
        raise RuntimeError(
            "Gemini returned a generic image brief instead of "
            f"a specific visual scene: {matched}"
        )

    # A useful visual brief should normally contain
    # multiple concrete production details.
    visual_detail_markers = [
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
        for marker in visual_detail_markers
        if marker in brief
    )

    if detail_count < 3:
        raise RuntimeError(
            "Gemini image_brief is too generic. "
            "A concrete scene with people, action, setting, "
            "objects and visual direction is required."
        )


def generate_post(
    api_key: str,
    model: str,
    topic: str,
    legal_sources: str,
    previous_context: str = "",
) -> dict[str, Any]:
    """
    Generate the legal post plus a production-ready visual brief.

    Gemini is used only for:
        1. legal content
        2. visual direction

    Image generation itself is performed by Cloudflare/FLUX.
    """

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing."
        )

    topic = (topic or "").strip()

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
الموضوع المطلوب:
{topic}

المصادر القانونية المتاحة:
{legal_sources or "لا توجد مصادر قانونية مضافة في الشيت."}

السياق السابق الاختياري:
{previous_context or "لا يوجد."}

============================================================
المطلوب 1: كتابة البوست
============================================================

اكتب بوستًا قانونيًا مصريًا طبيعيًا وجاهزًا للنشر.

يجب أن:
- يبدأ بموقف أو سؤال واقعي.
- يشرح المشكلة.
- يوضح القاعدة القانونية ببساطة.
- يعطي القارئ فائدة عملية.
- يحتوي CTA طبيعية إذا كانت مناسبة.
- لا يختلق أي معلومة قانونية.

============================================================
المطلوب 2: إعداد المشهد البصري
============================================================

بعد فهم الموضوع والبوست، صمّم مشهدًا واحدًا محددًا جدًا للصورة.

لا تفكر:
"ما الصورة القانونية المناسبة؟"

فكر:
"ما اللحظة الواقعية التي تلخص المشكلة القانونية بصريًا؟"

مثال توضيحي:
إذا كان الموضوع عن إيصال أمانة،
يمكن أن تكون هناك لحظة تسليم مستند بين طرفين في موقف حقيقي
مع وجود التردد أو القلق على وجه أحدهما.

لكن لا تنسخ المثال.
حلل الموضوع الفعلي أولًا.

حدد داخل image_brief:

- الشخصيات
- العمر التقريبي عند الحاجة
- ماذا يفعل كل شخص
- المستند/الشيء الرئيسي
- المكان
- الخلفية
- المشاعر
- اللحظة الدرامية
- زاوية الكاميرا
- نوع اللقطة
- الإضاءة
- عمق المجال
- التفاصيل المصرية المناسبة

image_brief:
- English only
- 80 to 180 words تقريبًا
- one scene only
- highly specific
- photorealistic
- editorial
- cinematic
- 4:5-friendly
- no text in the image
- no logos
- no watermark

ممنوع:
"professional legal image"
"lawyer in office"
"legal documents"
"justice scales"
"legal background"

هذه ليست Visual Briefs.

============================================================
مراجعة ذاتية قبل إخراج JSON
============================================================

اسأل نفسك:

1) هل الصورة مرتبطة مباشرة بالموضوع؟
2) هل يستطيع شخص رؤية الصورة وفهم الموقف العام؟
3) هل يوجد فعل حقيقي؟
4) هل يوجد عنصر رئيسي محدد؟
5) هل يوجد مكان حقيقي؟
6) هل يوجد شعور أو توتر واضح؟
7) هل يمكن لمصور محترف تنفيذ المشهد؟
8) هل تبدو كصورة صحفية/تحريرية وليست Graphic؟
9) هل تجنبت الرموز القانونية العامة؟
10) هل يمكن أن تكون الصورة مختلفة بوضوح عن صورة موضوع قانوني آخر؟

إذا كانت الإجابة لا على أي من هذه الأسئلة،
أعد تصميم image_brief قبل إخراج JSON.

أعد JSON فقط.
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
        "review_flags",
        "legal_sources_used",
    )

    for field in required_fields:

        if field not in data:
            raise RuntimeError(
                f"Gemini JSON is missing required field: "
                f"{field}"
            )

    # Normalize structured fields.
    data["review_flags"] = _normalize_list(
        data["review_flags"]
    )

    data["legal_sources_used"] = _normalize_list(
        data["legal_sources_used"]
    )

    data["post"] = (
        str(
            data["post"]
        )
        .strip()
    )

    data["image_brief"] = (
        str(
            data["image_brief"]
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

    # Production quality gate for visual direction.
    _validate_image_brief(
        data["image_brief"]
    )

    return data
