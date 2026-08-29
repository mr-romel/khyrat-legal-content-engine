from __future__ import annotations

from typing import Any

from google import genai

from gemini import (
    DEFAULT_TEXT_MODEL,
    SYSTEM_PROMPT,
    _extract_json,
    _normalize_list,
    _normalize_review_level,
    _validate_image_brief,
)


EDITORIAL_STYLE_PROMPT = """
قواعد الأسلوب الجديدة لصفحة اسأل محمود:

- اكتب كأنك محامٍ مصري بيشرح لحد عادي، مش بيكتب مذكرة أو بحث أكاديمي.
- استخدم العامية المصرية الخفيفة والواضحة في Facebook عندما لا تضر بالدقة القانونية.
- ابدأ من المشكلة التي تهم الشخص: "لو حصل معاك كذا..." أو سؤال طبيعي مشابه، وليس بمقدمة مدرسية.
- العنوان/الافتتاحية تكون قصيرة وطبيعية وتشد الانتباه بدون تهويل أو تخويف.
- ممنوع عناوين من نوع: "دليل شامل", "كل ما تريد معرفته", "تحذير خطير", "صدمة قانونية", "كارثة", "لازم تعرف", أو أي صياغة تبدو كإعلان أو Clickbait.
- لا تستخدم عناوين فرعية كثيرة، ولا تجعل كل سطر عنوانًا، ولا تحول المنشور إلى قائمة تعليمات آلية.
- تجنب الصياغات التي تكشف أو توحي بأن النص مولد آليًا، مثل: "فيما يلي", "إليك الدليل", "سنستعرض", "دعونا نتعرف", "الخلاصة", "أهم النقاط" بصورة نمطية.
- لا تكرر نفس Hook أو نفس تركيب الجمل في منشورات متتالية.
- نوّع البداية: سؤال، موقف يومي، خطأ شائع، مفاجأة قانونية هادئة، أو موقف قصير.
- استخدم المصطلح القانوني فقط عندما يكون مهمًا، ثم اشرحه بكلام الناس.
- خلي القارئ يفهم "يعني إيه الكلام ده؟" و"أعمل إيه؟" من غير ما يحتاج يعرف قانون.
- لا تضحِ بالدقة القانونية من أجل العامية أو التفاعل.
- لا تجعل كل منشور ينتهي بنفس CTA؛ يمكن أحيانًا إنهاء المنشور بخلاصة عملية قصيرة دون CTA أصلًا.
- ممنوع الإيموجي المفرط أو علامات التعجب المتكررة.
- الهدف: محتوى يبدو مكتوبًا بعناية بواسطة محامٍ مصري يعرف الناس وبيتكلم بلغتهم، وليس بواسطة قالب محتوى آلي.
"""


def generate_post(
    api_key: str,
    model: str,
    topic: str,
    legal_sources: str,
    previous_context: str = "",
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    topic = (topic or "").strip()
    if not topic:
        raise RuntimeError("Topic is empty.")

    selected_model = (model or DEFAULT_TEXT_MODEL).strip()
    if selected_model.startswith("models/"):
        selected_model = selected_model[len("models/"):]
    if not selected_model:
        selected_model = DEFAULT_TEXT_MODEL

    client = genai.Client(api_key=api_key)

    user_prompt = f"""
الموضوع:
{topic}

المصادر القانونية المتاحة:
{legal_sources or "لا توجد مصادر قانونية مدخلة."}

السياق السابق:
{previous_context or "لا يوجد."}

اكتب البوست النهائي.

ثم أنشئ image_brief لمشهد بصري واحد محدد.

وأخيرًا قيّم مستوى المراجعة القانونية طبقًا للقواعد الموجودة في System Prompt.

مهم جدًا:
لا توقف الموضوع لمجرد أنه حساس.
الهدف هو التمييز بين:
موضوع حساس يمكن شرحه بأمان
وبين ادعاء قانوني دقيق يحتاج تحققًا.

إذا احتجت ذكر عقوبة أو مادة أو رقم أو تاريخ محدد
ولا يوجد مصدر موثوق في المدخل:
إما احذف التفصيل من البوست واصغ الفكرة بشكل عام وآمن،
أو استخدم BLOCK إذا كان التفصيل جوهريًا ولا يمكن حذفه.

طبّق قواعد الأسلوب التحريري المرفقة، ولا تجعل البوست يبدو كأنه ناتج عن قالب AI.

راجع نفسك قبل إخراج JSON.
"""

    try:
        chat = client.chats.create(model=selected_model)
        response = chat.send_message(
            SYSTEM_PROMPT + "\n\n" + EDITORIAL_STYLE_PROMPT + "\n\n" + user_prompt
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini content generation failed: {exc}") from exc

    raw_text = (getattr(response, "text", None) or "").strip()
    if not raw_text:
        raise RuntimeError("Gemini returned an empty response.")

    data = _extract_json(raw_text)
    required_fields = (
        "post",
        "image_brief",
        "review_level",
        "review_flags",
        "legal_sources_used",
    )
    for field in required_fields:
        if field not in data:
            raise RuntimeError(f"Gemini JSON is missing required field: {field}")

    data["review_level"] = _normalize_review_level(data.get("review_level"))
    data["review_flags"] = _normalize_list(data.get("review_flags"))
    data["legal_sources_used"] = _normalize_list(data.get("legal_sources_used"))
    data["post"] = str(data.get("post", "") or "").strip()
    data["image_brief"] = str(data.get("image_brief", "") or "").strip()

    if not data["post"]:
        raise RuntimeError("Gemini returned an empty post.")
    _validate_image_brief(data["image_brief"])

    return data
