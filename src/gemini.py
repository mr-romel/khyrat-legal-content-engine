import json
import re
from typing import Any

from google import genai


SYSTEM_PROMPT = """
أنت المحرر القانوني الرئيسي لمحتوى "اسأل محمود" التابع للمحامي محمود خيرت.

هدفك:
إنتاج محتوى قانوني مصري احترافي، بسيط جدًا على المواطن العادي في مصر،
طبيعي في لغته، مفيد عمليًا، ويبدو كأنه مكتوب بواسطة محامٍ مصري حقيقي.

قواعد إلزامية للمحتوى:
1) اكتب بالعربية.
2) استخدم تعبيرات مصرية طبيعية عند الحاجة، بدون مبالغة.
3) ممنوع العبارات الآلية المحفوظة مثل:
   "في عالمنا اليوم"، "دعونا نتعرف"، "من الجدير بالذكر"،
   "في هذا المقال"، "لا شك أن".
4) لا تستخدم عناوين كثيرة أو نقاطًا كثيرة بلا داعٍ.
5) ابدأ بموقف أو سؤال واقعي يشد الانتباه.
6) اشرح القاعدة القانونية بلغة بسيطة ثم وضّح ماذا يفعل الشخص عمليًا.
7) لا تستخدم لغة قانونية معقدة إذا كان يمكن شرحها للعامة.
8) ممنوع اختلاق مادة قانونية أو حكم قضائي أو رقم قضية أو تاريخ.
9) إذا أعطيتك مصادر قانونية، التزم بها ولا تضف مصدرًا غير موجود من عندك.
10) إذا كانت نقطة قانونية تحتاج تحققًا ولم يوجد لها مصدر في المدخل،
    اذكر "يحتاج مراجعة قانونية" داخل review_flags ولا تخترع المعلومة.
11) لا تذكر أنك ذكاء اصطناعي ولا تتحدث عن طريقة توليد النص.
12) تجنب التكرار والجمل النمطية.
13) اجعل الدعوة للتفاعل CTA طبيعية وغير بيعية.
14) استهدف تقريبًا 180 إلى 320 كلمة، إلا إذا كان الموضوع يحتاج أقل.
15) استخدم 2 إلى 4 هاشتاجات كحد أقصى عند الحاجة.
16) لا تضع روابط أو مراجع وهمية.

قواعد إلزامية للوصف البصري:
17) image_brief ليس نصًا سيظهر على الصورة.
18) اكتب image_brief كتوجيه احترافي لمولد صور AI.
19) الصورة يجب أن تكون مشهدًا بصريًا حقيقيًا مرتبطًا بالمشكلة القانونية،
    وليس Poster أو Infographic أو Screenshot أو كارت نصي.
20) لا تضع أي نص مكتوب داخل الصورة.
21) ممنوع كتابة عنوان الموضوع أو شرح الموضوع أو فقرات أو هاشتاجات داخل الصورة.
22) لا تستخدم ميزان العدالة كعنصر رئيسي بشكل تلقائي؛ استخدمه فقط لو كان له معنى بصري حقيقي.
23) اختر مشهدًا مختلفًا حسب طبيعة الموضوع.
24) ركّز على الأشخاص، المستندات، الموقف، المكان، التعبير، الإضاءة
    والرموز البصرية التي توضح المشكلة.
25) اجعل الصورة مناسبة لمنشور Facebook احترافي لمكتب محاماة مصري.
26) الصورة عمودية بنسبة 4:5، تكوين واضح، subject رئيسي واحد،
    خلفية مرتبة، تفاصيل واقعية، وإضاءة احترافية.
27) لا تجعل المشهد يبدو كصورة Stock رخيصة أو صورة دعائية مبتذلة.
28) لا تضف شعارات أو أسماء محامين أو نصوص أو Watermark؛ الهوية تضاف لاحقًا
    إذا احتجنا ذلك خارج مولد الصور.
29) image_brief يجب أن يكون باللغة الإنجليزية لأن مولد الصور يتعامل معها
    بشكل أفضل في هذا الـpipeline.

أعد JSON فقط، بدون Markdown وبدون ```json.

الشكل المطلوب:
{
  "post": "النص النهائي الجاهز للنشر",
  "image_brief": "احترافي باللغة الإنجليزية، صالح مباشرة لمولد الصور",
  "review_flags": ["ملاحظات المراجعة"],
  "legal_sources_used": ["المصادر القانونية المستخدمة"]
}
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise RuntimeError(
                "Gemini did not return a JSON object. "
                f"Raw response: {text[:1500]}"
            )

        candidate = text[start : end + 1]

        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Gemini returned invalid JSON. "
                f"Raw response: {text[:1500]}"
            ) from exc


def generate_post(
    api_key: str,
    model: str,
    topic: str,
    legal_sources: str,
    previous_context: str = "",
) -> dict[str, Any]:
    client = genai.Client(api_key=api_key)

    selected_model = (model or "").strip().strip("/")

    # Keep the production default resilient even if the GitHub Secret
    # is accidentally missing or left blank.
    if not selected_model or selected_model == "models/":
        selected_model = "gemini-3.6-flash"

    if selected_model.startswith("models/"):
        selected_model = selected_model[len("models/") :]

    user_prompt = f"""
الموضوع المطلوب:
{topic}

المصادر القانونية التي يجب الالتزام بها إن وجدت:
{legal_sources or "لا توجد مصادر قانونية مضافة في الشيت."}

سياق سابق اختياري لتجنب التكرار:
{previous_context or "لا يوجد."}

اكتب البوست النهائي الآن.

ثم صمّم مفهومًا بصريًا مناسبًا لهذا الموضوع تحديدًا.
لا تكرر مجرد عنوان الموضوع داخل image_brief.
فكر في "ما المشهد الذي لو رآه المواطن بدون قراءة النص سيفهم المشكلة أو يشعر بها؟"

مثال لطريقة التفكير فقط:
- لو الموضوع عن إيصال أمانة: مشهد تسليم مستند/إيصال بين شخصين في موقف واقعي متوتر.
- لو الموضوع عن عقد: مشهد شخص يراجع عقدًا ويكتشف بندًا خطيرًا.
- لو الموضوع عن فصل موظف: مشهد موظف يتلقى قرارًا من جهة العمل في سياق واقعي.
- لو الموضوع عن ميراث: مشهد أفراد أسرة أمام مستندات تركة وتقسيم رسمي.

لا تنسخ الأمثلة حرفيًا، وابتكر مشهدًا مناسبًا للموضوع الفعلي.

image_brief يجب أن يكون:
- باللغة الإنجليزية
- وصفًا بصريًا فقط
- مناسبًا لمولد صور احترافي
- بدون أي نص داخل الصورة
- بدون شرح قانوني داخل الصورة
- بدون كتابة العنوان
- بدون watermark
- cinematic / realistic / professional
- Egyptian context where relevant
- vertical 4:5 composition
"""

    response = client.models.generate_content(
        model=selected_model,
        contents=SYSTEM_PROMPT + "\n\n" + user_prompt,
    )

    raw_text = (getattr(response, "text", None) or "").strip()

    if not raw_text:
        raise RuntimeError("Gemini returned an empty response.")

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
        data["review_flags"] = [str(data["review_flags"])]

    if not isinstance(data["legal_sources_used"], list):
        data["legal_sources_used"] = [str(data["legal_sources_used"])]

    data["post"] = str(data["post"]).strip()
    data["image_brief"] = str(data["image_brief"]).strip()

    if not data["post"]:
        raise RuntimeError("Gemini returned an empty post.")

    if not data["image_brief"]:
        raise RuntimeError("Gemini returned an empty image brief.")

    return data
