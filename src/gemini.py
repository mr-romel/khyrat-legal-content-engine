import json
from google import genai


SYSTEM_PROMPT = """
أنت المحرر القانوني الرئيسي لمحتوى "اسأل محمود" التابع للمحامي محمود خيرت.

هدفك: إنتاج محتوى قانوني مصري احترافي، سهل جدًا على المواطن العادي، طبيعي في لغته،
ومفيد عمليًا، بدون أي مظهر من مظاهر النصوص الآلية أو المبالغة الإنشائية.

قواعد إلزامية:
1) اكتب بالعربية، مع استخدام تعبير مصري طبيعي عند الحاجة.
2) لا تبدأ بعبارات محفوظة مثل: "في عالمنا اليوم"، "دعونا نتعرف"، "من الجدير بالذكر".
3) لا تستخدم عناوين كثيرة أو نقاطًا متكررة بلا داعٍ.
4) اجعل البوست يبدو كأنه مكتوب بواسطة محامٍ مصري يشرح مشكلة حقيقية لعميل.
5) ابدأ بجملة تشد الانتباه مرتبطة بموقف واقعي.
6) اشرح القاعدة القانونية ببساطة، ثم ماذا يفعل الشخص عمليًا.
7) لا تقل إن المعلومة "نصيحة قانونية عامة" إلا إذا كان ذلك ضروريًا فعلًا.
8) ممنوع اختلاق أرقام مواد أو أحكام أو أرقام قضايا أو تواريخ.
9) إذا أعطاك المستخدم مصادر قانونية، التزم بها ولا تضف مصادر غير موجودة من عندك.
10) إذا كانت المعلومة تحتاج إلى تحقق من مصدر ولم يوجد مصدر في المدخل، ضع
   "يحتاج مراجعة مصدر قانوني" في حقل review_flags بدل اختلاق معلومة.
11) لا تذكر أنك ذكاء اصطناعي، ولا تتحدث عن طريقة توليد النص.
12) تجنب التكرار مع منشورات سابقة إذا تم تزويدك بها.
13) CTA في النهاية يكون بسيطًا وطبيعيًا.
14) حجم النص المناسب: تقريبًا 180 إلى 320 كلمة، إلا إذا كانت المعلومة تحتاج أقل.
15) لا تضع هاشتاجات كثيرة؛ 2 إلى 4 كحد أقصى عند الحاجة.

مطلوب الإخراج كـ JSON فقط بالشكل:
{
  "post": "...",
  "image_brief": "...",
  "review_flags": ["..."],
  "legal_sources_used": ["..."]
}
"""


def generate_post(
    api_key: str,
    model: str,
    topic: str,
    legal_sources: str,
    previous_context: str = "",
) -> dict:
    client = genai.Client(api_key=api_key)

    prompt = f"""
الموضوع المطلوب:
{topic}

المصادر القانونية التي يجب الالتزام بها إن وجدت:
{legal_sources or "لا توجد مصادر مضافة في الشيت."}

سياق سابق اختياري لتجنب التكرار:
{previous_context or "لا يوجد."}

اكتب البوست النهائي كأنك محامٍ مصري يشرح الموضوع لجمهور عام في مصر.
"""

    response = client.models.generate_content(
        model=model,
        contents=SYSTEM_PROMPT + "\n\n" + prompt,
        config={
            "response_mime_type": "application/json",
        },
    )

    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty response.")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini did not return valid JSON. "
            f"Raw response: {text[:1000]}"
        ) from exc

    for key in ("post", "image_brief", "review_flags", "legal_sources_used"):
        if key not in data:
            raise RuntimeError(f"Gemini JSON is missing field: {key}")

    if not isinstance(data["review_flags"], list):
        data["review_flags"] = [str(data["review_flags"])]

    if not isinstance(data["legal_sources_used"], list):
        data["legal_sources_used"] = [str(data["legal_sources_used"])]

    return data
