from __future__ import annotations

import json
import re
from typing import Any

from ai_router import create_client, has_any_provider_key

FIXED_SLOGAN = "خليك فاكر دايما ... اسأل محمود"

REEL_SCRIPT_PROMPT = """أنت كاتب ريلز قانونية مصرية قصيرة جدًا، جذابة ومباشرة، لصالح «اسأل محمود».
المطلوب نص منطوق فقط، لا مقال ولا شرح مطوّل.

الترتيب الإلزامي 4 أجزاء فقط:
1) hook: سؤال افتتاحي قوي ومحدد يوقف المشاهد من أول ثانية. نوّع زاوية السؤال في كل مرة حسب الموضوع: خسارة محتملة، حق مهدد، خطأ شائع، موقف مفاجئ، أو «تعمل إيه لو...؟». لا تستخدم افتتاحية عامة ولا تعِد نفس صياغة الهوك حرفيًا بين المواضيع.
2) answer: إجابة مباشرة على السؤال من أول جملة، ثم أهم خطوة أو خطوتين عمليتين فقط. اختصر بلا حشو أو تكرار. لا تخترع نصوصًا أو مواعيد أو عقوبات قانونية.
3) cta: طلب واحد قصير وواضح، مرتبط بالموضوع (مثال: «اكتب سؤالك في التعليقات» أو «تابعني لمعلومة قانونية تهمك»). لا تطلب من المشاهد الرجوع إلى منشور أو بوست أو رابط أو مصدر غير مذكور صراحة.
4) end_slogan: النص الصوتي الحرفي في النهاية هو: «خليك فاكر دايما ... اسأل محمود».
5) outro_visual: وصف إلزامي ثابت لخاتمة الفيديو: «صورة اللوجو الأصلية تظهر وحدها بملء الشاشة في نهاية الفيديو، مع تشغيل السلوجن الصوتي خليك فاكر دايما ... اسأل محمود». لا تنشئ لوجو بديلًا ولا تضع نصًا بديلًا.

قواعد صارمة:
- استهدف 12–20 ثانية؛ الحد الأقصى 55 كلمة قبل السلوجن، والحد الأقصى 3 جمل في الإجابة.
- الهوك سؤال باللهجة المصرية، قصير (حتى 12 كلمة)، محدد للموضوع، ويثير فضولًا حقيقيًا دون تهويل كاذب.
- الإجابة تبدأ بالمعلومة المفيدة فورًا، لا تقل «الموضوع مهم» أو «خلينا نفهم» أو مقدمات مشابهة.
- ممنوع الحشو، التكرار، المقدمات، التحيات، العناوين المنطوقة، تعليمات التصوير، وعبارات مثل «ارجع للمنشور»، «شوف البوست»، «زي ما قولنا قبل كده».
- استخدم العامية المصرية الطبيعية، وجملًا قصيرة سهلة الإلقاء.
- لا تقدّم رأيًا قانونيًا قطعيًا إذا كانت المعلومات غير كافية؛ وضّح القيد في كلمات قليلة.
- أخرج JSON صالحًا فقط بالمفاتيح: hook, answer, cta, end_slogan, full_script, estimated_seconds, outro_visual.
- full_script يجمع السؤال، ثم الإجابة، ثم CTA، ثم السلوجن بهذا الترتيب، من غير تسميات أو شرح إضافي.
"""

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
    required = ("hook", "answer", "cta", "end_slogan", "full_script")
    for key in required:
        if not str(data.get(key) or "").strip():
            raise ValueError(f"Reel script is missing required section: {key}")

    hook = str(data["hook"]).strip()
    answer = str(data["answer"]).strip()
    cta = str(data["cta"]).strip()
    if len(hook.split()) > 12:
        raise ValueError("Reel hook must be 12 words or fewer.")
    if not ("؟" in hook or "?" in hook):
        raise ValueError("Reel hook must be a question.")
    if len(answer.split()) > 40:
        raise ValueError("Reel answer is too long; maximum is 40 words.")
    if len(cta.split()) > 12:
        raise ValueError("Reel CTA must be 12 words or fewer.")
    forbidden = ("ارجع للمنشور", "شوف البوست", "ارجع للبوست", "في المنشور", "في البوست")
    combined = " ".join((hook, answer, cta)).casefold()
    if any(phrase in combined for phrase in forbidden):
        raise ValueError("Reel script refers to an unspecified post or publication.")

    data["hook"] = hook
    data["answer"] = answer
    data["cta"] = cta
    data["end_slogan"] = FIXED_SLOGAN
    data["full_script"] = "\n\n".join((hook, answer, cta, FIXED_SLOGAN))
    try:
        seconds = int(data.get("estimated_seconds", 18))
    except (TypeError, ValueError):
        seconds = 18
    data["estimated_seconds"] = max(10, min(seconds, 30))
    return data


def generate_reel_script(
    *,
    api_key: str,
    model: str,
    topic: str,
    legal_sources: str = "",
    source_post: str = "",
    target_seconds: int = 18,
) -> dict[str, Any]:
    """Generate a concise question-answer-CTA-slogan script for a legal reel."""
    if not api_key and not has_any_provider_key():
        raise RuntimeError("No text AI provider is configured.")
    topic = str(topic or "").strip()
    if not topic:
        raise ValueError("Reel topic is empty.")

    client = create_client(api_key=api_key, task="text")
    selected_model = str(model or "gemini-3.6-flash").strip().removeprefix("models/")
    prompt = f"""{REEL_SCRIPT_PROMPT}

الموضوع: {topic}
المدة المستهدفة بالثواني: {max(10, min(int(target_seconds), 30))}
نص المصدر المتاح (استخدمه لفهم الموضوع فقط، ولا تطلب من المشاهد الرجوع إليه):
{source_post or "غير متاح"}

المصادر/الملاحظات القانونية المتحققة:
{legal_sources or "لا توجد مصادر مرفقة؛ تجنب التفاصيل الرقمية أو القطعية غير المتحققة."}

اكتب سؤالًا افتتاحيًا مختلف الصياغة ومشدودًا للموضوع، ثم إجابة مفيدة مباشرة، ثم CTA واحدًا، ثم السلوجن الثابت. احذف أي جملة لا يحتاجها المشاهد.
"""
    response = client.models.generate_content(
        model=selected_model,
        contents=prompt,
        config={"response_mime_type": "application/json", "temperature": 0.85},
    )
    raw = str(getattr(response, "text", "") or "").strip()
    return validate_reel_script(_extract_json(raw))
