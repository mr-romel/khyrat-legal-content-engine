import json
import re

from google import genai


SYSTEM_PROMPT = """
أنت المحرر القانوني الرئيسي لمحتوى "اسأل محمود" التابع للمحامي محمود خيرت.

هدفك:
إنتاج محتوى قانوني مصري احترافي، بسيط جدًا على المواطن العادي في مصر،
طبيعي في لغته، مفيد عمليًا، ويبدو كأنه مكتوب بواسطة محامٍ مصري حقيقي.

قواعد إلزامية:
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

مهم جدًا:
أعد JSON فقط، بدون Markdown وبدون ```json.

الشكل المطلوب:
{
  "post": "النص النهائي الجاهز للنشر",
  "image_brief": "وصف بصري للصورة",
  "review_flags": ["ملاحظات المراجعة"],
  "legal_sources_used": ["المصادر القانونية المستخدمة"]
}
"""


def _extract_json(text: str) -> dict:
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
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise RuntimeError(
                "Gemini did not return a JSON object. "
                f"Raw response: {text[:1500]}"
            )

        candidate = text[start:end + 1]

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

    return data
