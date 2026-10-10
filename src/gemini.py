from __future__ import annotations

import json
import re
from typing import Any

from google import genai


DEFAULT_TEXT_MODEL = "gemini-3.6-flash"
MAX_GENERATION_ATTEMPTS = 3

SYSTEM_PROMPT = """
أنت رئيس تحرير المحتوى القانوني والمخرج الإبداعي البصري لصفحة «اسأل محمود» التابعة للمحامي محمود خيرت.

اكتب محتوى قانوني مصري احترافي، بسيط، طبيعي، ويبدو مكتوبًا بواسطة محامٍ مصري حقيقي.
- اكتب بالعربية، واستخدم مصرية مهنية طبيعية عند الحاجة.
- ابدأ بموقف أو سؤال واقعي، ثم اشرح القاعدة ببساطة وأثرها العملي.
- لا تختلق مادة أو حكمًا أو رقمًا أو تاريخًا أو عقوبة أو مصدرًا.
- البحث القانوني جزء أساسي من إعداد كل منشور، وليس خطوة اختيارية: افحص دائمًا أحدث تشريع نافذ وأحدث تعديل ذي صلة قبل الكتابة.
- إذا كان الموضوع متصلًا بقانون عُدّل حديثًا، لا تعتمد على الصياغة القديمة لمجرد أنها شائعة؛ اعتمد النص النافذ وتاريخ بدء العمل به متى كان ذلك ثابتًا في المصادر.
- استخدم أحكام ومبادئ محكمة النقض أو المحكمة الإدارية العليا عندما يكون هناك مصدر متحقق ومرتبط مباشرة بالموضوع.
- عند وجود حكم مناسب، أدرج في المحتوى مقتطفًا قصيرًا فقط من النص المتحقق، مع ذكر المحكمة ورقم الطعن وتاريخ الجلسة إذا كانت البيانات متاحة في المصدر.
- إذا لم يتوفر نص حكم موثق، يمكن ذكر مبدأ قضائي مستقر بصياغة دقيقة، لكن ممنوع اختراع رقم طعن أو نسبة مبدأ لمحكمة دون مصدر.
- لا تستخدم حكمًا قديمًا لتفسير نص تشريعي أُلغي أو عُدّل دون التنبيه إلى ذلك والتحقق من استمرار صلاحيته.
- لا تعتبر رقم الطعن أو تاريخ الحكم صحيحًا لمجرد ظهوره في سياق غير رسمي؛ الأولوية للمصدر القضائي الرسمي أو مصدر قانوني موثوق يورد البيانات بوضوح.
- الموضوع الحساس لا يعني إيقاف النشر تلقائيًا؛ إذا كانت التفاصيل الدقيقة غير متحققة احذفها أو عمّمها متى أمكن.
- CTA ناعمة وغير بيعية، تربط بين اختلاف الوقائع والمستندات وبين ضرورة مراجعة الموقف قبل القرار المهم.
- لا تستخدم «احجز استشارة» أو «تواصل معي» أو «كلمني» أو أي صيغة بيع مباشر.
- تجنب العبارات الآلية المحفوظة والتكرار والحشو.
- لا تستخدم النقط المتتابعة (...) أو (…) في المنشور، ولا تنه المنشور بجملة ناقصة أو بحرف عطف أو كلمة تدل على استمرار الكلام. كل منشور يجب أن ينتهي بفكرة مكتملة وعلامة ترقيم طبيعية.
- ممنوع استخدام علامات التنصيص العربية أو الإنجليزية في النص النهائي، بما فيها « » و" " و“ ”، إلا إذا كان نقل نص قانوني حرفيًا ضروريًا ومسموحًا به؛ وفي هذه الحالة أعد الصياغة بدل الاقتباس.
- ممنوع وضع نقطة في نهاية أي جملة في المنشور أو التعليق. استخدم الفواصل وعلامات الاستفهام والتعجب عند الحاجة، واجعل نهاية كل جملة طبيعية من دون نقطة ختامية.
- ممنوع تمامًا أي تعبير يلمّح إلى أن النص مولد آليًا أو مكتوب بواسطة ذكاء اصطناعي، مثل ذكاء اصطناعي، نموذج لغوي، محتوى مولد، مولد آلي، تم توليد النص، أو أي حديث عن طريقة الإنتاج
- لا تستخدم القوالب المتكررة أو العبارات التي تبدو كأنها تعليمات نموذج أو مخرجات آلية. اكتب كأن النص خرج مباشرة من مكتب محامٍ مصري له خبرة عملية وصوت شخصي واضح.
- لا تستخدم لغة تسويقية مصطنعة، ولا افتتاحيات عامة محفوظة، ولا عبارات ختامية نمطية من نوع في النهاية، باختصار، وهنا تأتي أهمية، لا شك أن، من المهم أن نعرف، في عالم الأعمال اليوم، أو أي بديل متكرر لها.
- لا تجعل الفقرات متساوية الطول أو الإيقاع. غيّر طول الجمل، واسمح بانتقالات بشرية طبيعية، مع الحفاظ على الدقة القانونية.
- LinkedIn يجب أن ينتهي قبل الهاشتاجات بفكرة مكتملة، ثم يضاف إليه لاحقًا من النظام عدد محدود من الهاشتاجات العربية المرتبطة فعليًا بالموضوع

image_brief يجب أن يكون بالإنجليزية فقط، مشهدًا واحدًا محددًا، واقعيًا، سينمائيًا، تحريريًا، مرتبطًا مباشرة بمضمون الموضوع والمنشور، وبدون نص أو شعار أو علامة مائية داخل الصورة.
- الصور لمحتوى قانوني معاصر في مصر: المقصود مصر الحديثة اليوم، وليس مصر القديمة.
- ممنوع تمامًا الستايل الفرعوني أو التاريخي: الأهرامات، المعابد، التوابيت، الهيروغليفية، التماثيل القديمة، الأزياء الفرعونية، الآثار أو أي رموز مصر القديمة، إلا إذا كان موضوع المنشور نفسه عن الآثار أو التاريخ المصري القديم.
- اختر مشهدًا واقعيًا معاصرًا تدعمه الوقائع القانونية المذكورة: شارع أو شركة أو منزل أو متجر أو جهة عمل أو هاتف أو مستندات حديثة بحسب الموضوع، ولا تضف محكمة أو محاميًا أو ميزان عدالة تلقائيًا.
- اجعل الصورة وثائقية تحريرية حديثة، بتفاصيل بشرية ومكانية منطقية، ومن دون أي كتابة مقروءة داخل الصورة.
image_mode يجب أن يكون CONTEXT_ONLY افتراضيًا، ويُستخدم REFERENCE_SUBJECT فقط عندما تكون هناك صورة مرجعية فعلية ومتاحة ومطلوبة للمشهد.
الأولوية هي دقة المشهد وارتباطه المباشر بالموضوع، وليس إجبار المحامي على الظهور في كل صورة.
إذا كان ظهور المحامي طبيعيًا ومفيدًا للمشهد وكان مرجع الشخصية متاحًا، يمكن استخدام REFERENCE_SUBJECT.
إذا لم يكن ذلك ضروريًا، استخدم CONTEXT_ONLY ولا تعتبر غياب صورة المحامي مشكلة.
لا تجعل المرجع يغيّر الواقعة القانونية أو يحول الصورة إلى بورتريه دعائي.
إذا كان المشهد يتضمن الشخصية المرجعية، صمّم وضعية جديدة وبيئة جديدة وزاوية كاميرا جديدة وتكوينًا جديدًا وملابس مناسبة للسياق؛ لا تقلّد وضعية أو خلفية أو أثاث أو إضاءة أو framing الصور المرجعية.

أعد JSON فقط بهذا الشكل:
{
  "post": "...",
  "image_brief": "...",
  "image_mode": "CONTEXT_ONLY",
  "review_level": "CLEAR|REVIEW",
  "review_flags": [],
  "legal_sources_used": [],
  "hook_pattern": "question|incident|surprise_fact|common_mistake|practical_scenario|client_problem|legal_rule|contrast|narrative|conclusion_first"
}
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"Gemini did not return a valid JSON object. Raw response: {text[:2000]}")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned invalid JSON. Raw response: {text[:2000]}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Gemini JSON response is not an object.")
    return data


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _normalize_review_level(value: Any) -> str:
    level = str(value or "").strip().upper()
    return level if level in {"CLEAR", "REVIEW"} else "REVIEW"


def _validate_image_brief(image_brief: str) -> None:
    brief = image_brief.strip().lower()
    if not brief:
        raise RuntimeError("Gemini returned an empty image_brief.")
    generic = (
        "professional legal image", "professional law image", "legal background",
        "lawyer at desk", "generic legal image", "generic justice scales",
        "abstract legal background", "legal themed image", "legal concept",
    )
    matched = [phrase for phrase in generic if phrase in brief]
    if matched:
        raise RuntimeError(f"Gemini returned a generic image brief: {matched}")
    markers = (
        "person", "people", "man", "woman", "document", "paper", "room", "office",
        "street", "hands", "expression", "body language", "camera", "lighting",
        "close-up", "medium shot", "background",
    )
    if sum(1 for marker in markers if marker in brief) < 3:
        raise RuntimeError("Gemini image_brief is too generic.")


def _post_quality_ok(post: str) -> bool:
    text = re.sub(r"\s+", " ", str(post or "")).strip()
    words = re.findall(r"\S+", text)
    # This is the pre-editorial generation gate. LinkedIn is produced separately
    # by editorial_review, so this gate must not reject usable source content merely
    # because Gemini chose a different natural CTA wording.
    return len(text) >= 650 and len(words) >= 120


def _soft_cta_present(post: str) -> bool:
    text = str(post or "").casefold()
    markers = (
        "التفاصيل", "الوقائع", "المستند", "مراجعة", "قبل ما تاخد قرار",
        "قبل اتخاذ القرار", "محامٍ", "محامي", "موقفك القانوني", "القرار القانوني",
        "القرار", "الموقف القانوني",
    )
    return any(marker in text for marker in markers)


def _validate_data(data: dict[str, Any]) -> dict[str, Any]:
    for field in ("post", "image_brief", "image_mode", "review_level", "review_flags", "legal_sources_used", "hook_pattern"):
        if field not in data:
            raise RuntimeError(f"Gemini JSON is missing required field: {field}")
    data["image_mode"] = str(data.get("image_mode", "CONTEXT_ONLY")).strip().upper()
    if data["image_mode"] not in {"CONTEXT_ONLY", "REFERENCE_SUBJECT"}:
        data["image_mode"] = "CONTEXT_ONLY"
    data["review_level"] = _normalize_review_level(data.get("review_level"))
    data["review_flags"] = _normalize_list(data.get("review_flags"))
    data["legal_sources_used"] = _normalize_list(data.get("legal_sources_used"))
    allowed_hooks = {"question","incident","surprise_fact","common_mistake","practical_scenario","client_problem","legal_rule","contrast","narrative","conclusion_first"}
    data["hook_pattern"] = str(data.get("hook_pattern", "")).strip().lower()
    if data["hook_pattern"] not in allowed_hooks:
        raise RuntimeError("Gemini returned an invalid hook_pattern.")
    data["post"] = str(data.get("post", "")).strip()
    data["image_brief"] = str(data.get("image_brief", "")).strip()
    if not data["post"]:
        raise RuntimeError("Gemini returned an empty post.")
    _validate_image_brief(data["image_brief"])
    return data


def _generate_once(client: Any, selected_model: str, prompt: str) -> dict[str, Any]:
    response = client.models.generate_content(
        model=selected_model,
        contents=SYSTEM_PROMPT + "\n\n" + prompt,
        config={"max_output_tokens": 8192},
    )
    raw_text = (getattr(response, "text", None) or "").strip()
    if not raw_text:
        raise RuntimeError("Gemini returned an empty response.")
    return _validate_data(_extract_json(raw_text))


def generate_image_scene_from_post(api_key: str, model: str, post: str) -> str:
    """Derive one concrete visual scene from the final post only."""
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    post = " ".join(str(post or "").split()).strip()
    if not post:
        raise RuntimeError("Final post content is required.")
    selected_model = (model or DEFAULT_TEXT_MODEL).strip().removeprefix("models/") or DEFAULT_TEXT_MODEL
    client = genai.Client(api_key=api_key)
    prompt = f"""
Transform the FINAL POST below into one concrete, image-ready scene description.

STRICT RULES:
- The final post is the ONLY semantic source.
- Extract the specific situation, people, actions, setting, and visible evidence described by the post.
- Convert abstract legal explanations into the closest direct visual representation supported by the post.
- Never add a generic courtroom, lawyer, law books, justice scales, office, contract, police scene, or other legal stock imagery unless the post itself supports it.
- This is contemporary Egypt, not ancient Egypt. Explicitly exclude pharaonic or historical Egyptian styling: pyramids, temples, hieroglyphs, sarcophagi, ancient statues, ancient costumes, archaeological ruins, papyrus, and ancient motifs. Only include these when the post is specifically about ancient Egyptian history or antiquities.
- Prefer a plausible present-day Egyptian setting and modern objects only when the post supports them; depict the exact legal situation rather than stereotypical national symbols.
- Never invent people, actions, documents, locations, events, numbers, logos, or facts.
- Use one scene only, not a collage or multiple panels.
- Describe subject, action, setting, important visual evidence, composition, camera angle, and lighting.
- English only.
- No readable text, letters, numbers, logos, captions, watermarks, UI, or infographic elements in the image.

FINAL POST:
{post}

Return only the English visual scene description.
"""
    response = client.models.generate_content(
        model=selected_model,
        contents=prompt,
        config={"max_output_tokens": 1200},
    )
    scene = " ".join(str(getattr(response, "text", "") or "").split()).strip()
    if len(scene) < 80:
        raise RuntimeError("Visual scene description is too short.")
    generic = ("generic legal", "professional legal image", "legal concept",
               "lawyer at desk", "justice scales", "law books", "legal background")
    if any(term in scene.lower() for term in generic):
        raise RuntimeError("Visual scene description is generic.")
    return scene


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
    selected_model = (model or DEFAULT_TEXT_MODEL).strip().removeprefix("models/") or DEFAULT_TEXT_MODEL
    client = genai.Client(api_key=api_key)

    base_prompt = f"""
الموضوع:
{topic}

المصادر القانونية المتاحة:
{legal_sources or "لا توجد مصادر قانونية مدخلة."}

السياق السابق لتجنب التكرار:
{previous_context or "لا يوجد."}

اكتب مسودة قانونية جاهزة لكي تمر على المراجع القانوني والتحرير النهائي.
استهدف تقريبًا 180 إلى 320 كلمة، لكن لا تحشو النص فقط للوصول إلى رقم. اجعل الصياغة بشرية ومتفاوتة الإيقاع، ولا تكرر نفس البناء من منشور إلى آخر.
قبل الكتابة، اختر Hook Pattern واحدًا مناسبًا فعلًا للموضوع والزاوية والهدف، ولا تستخدم نفس نمط الافتتاح المستخدم في المنشورات السابقة الواردة في السياق. الخيارات: سؤال مباشر، واقعة قانونية، معلومة مفاجئة، خطأ شائع، سيناريو عملي، مشكلة عميل، قاعدة قانونية، مفارقة/مقارنة، افتتاحية سردية، أو نتيجة/استنتاج يبدأ منه البوست. المطلوب تغيير بنية الدخول نفسها، وليس تبديل كلمات القالب فقط. لا تبدأ كل المنشورات بصيغ محفوظة مثل "لو..." أو "ناس كتير..." أو "خليني أقولك...".
أنشئ الافتتاح من صلب الموضوع، ثم اشرح الفكرة، وضّح الأثر العملي، وأنهِ بـCTA طبيعية غير بيعية.
إذا لم تكن معلومة دقيقة متحققة، لا تخترعها؛ احذفها أو صغها بصورة عامة وآمنة.
أنشئ أيضًا image_brief مناسبًا للمشهد نفسه. يجب أن يكون image_mode=REFERENCE_SUBJECT؛ وإذا لم يكن ظهور الشخص المرجعي طبيعيًا ومباشرًا في المشهد القانوني، استخدم review_level=REVIEW بدلًا من CONTEXT_ONLY.
"""

    retry_prompt = base_prompt + """

مراجعة جودة قبل الإخراج:
تأكد أن المنشور مفيد ومتماسك وليس مختصرًا بشكل مخل، وأن نهايته تتضمن إشارة طبيعية إلى اختلاف الوقائع أو المستندات أو ضرورة مراجعة الموقف قبل القرار المهم.
لا تستخدم صيغة بيع مباشر.
"""

    last_error: Exception | None = None
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        try:
            data = _generate_once(client, selected_model, base_prompt if attempt == 1 else retry_prompt)
            if _post_quality_ok(data["post"]) and _soft_cta_present(data["post"]):
                return data
            if _post_quality_ok(data["post"]):
                data["post"] = data["post"].rstrip() + "\n\nوالتفاصيل والوقائع والمستندات قد تغيّر التقييم القانوني، لذلك مراجعة الموقف قبل اتخاذ قرار مهم قد تكون فارقة."
                if _post_quality_ok(data["post"]):
                    return data
            last_error = RuntimeError("Gemini returned content below the pre-editorial quality threshold.")
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Gemini content generation failed after {MAX_GENERATION_ATTEMPTS} attempts: {last_error}")
