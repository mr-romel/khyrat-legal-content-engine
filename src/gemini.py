from __future__ import annotations

import json
import re
from typing import Any

from ai_router import create_client, has_any_provider_key


DEFAULT_TEXT_MODEL = "gemini-3.6-flash"
MAX_GENERATION_ATTEMPTS = 3

SYSTEM_PROMPT = """
أنت رئيس تحرير المحتوى القانوني والمخرج الإبداعي البصري لصفحة «اسأل محمود» التابعة للمحامي محمود خيرت.

اكتب محتوى قانوني مصري احترافي، بسيط، طبيعي، ويبدو مكتوبًا بواسطة محامٍ مصري حقيقي.
- اكتب بالعربية، واستخدم مصرية مهنية طبيعية عند الحاجة.
- ابدأ بموقف أو سؤال واقعي، ثم اشرح القاعدة ببساطة وأثرها العملي.
- لا تختلق مادة أو حكمًا أو رقمًا أو تاريخًا أو عقوبة أو مصدرًا.
- لا تذكر اسم قانون أو رقم مادة أو رقم طعن أو تاريخ جلسة إلا إذا كان ظاهرًا بوضوح في نص مصدر مسترجع داخل حزمة البحث القانونية؛ مجرد وجوده في ملاحظات قديمة أو ذاكرة النموذج لا يكفي.
- إذا لم يثبت المرجع المحدد، احذف الإحالة الدقيقة واشرح المبدأ بصياغة عامة مقيدة، ولا تنشئ اسمًا عامًا لتشريع غير محدد.
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
- ممنوع إدراج كلمات تخطيطية أو عناوين داخلية مثل Checklist أو check list أو زاوية أخرى أو زاوية جديدة أو زاوية المحتوى أو Hook أو CTA أو عنوان خطة المحتوى داخل المنشور النهائي. اكتب المحتوى النهائي مباشرة دون وصف استراتيجية الكتابة.
- LinkedIn يجب أن ينتهي قبل الهاشتاجات بفكرة مكتملة، ثم يضاف إليه لاحقًا من النظام عدد محدود من الهاشتاجات العربية المرتبطة فعليًا بالموضوع

لا تنشئ وصف الصورة ضمن مهمة كتابة المنشور؛ سيُولّد وصف الصورة في مهمة مساعدة مستقلة بعد اكتمال المنشور، لتوفير حصة Gemini للكتابة القانونية.

معيار إعداد المحتوى قبل الكتابة — INTERNAL EDITORIAL BRIEF:
- حلّل الكلمة/السؤال الأساسي، ونية الباحث، والجمهور الذي يطرح السؤال، والنتيجة العملية التي يريد الوصول إليها. استخدم ذلك داخليًا لتحديد زاوية المنشور، ولا تطبع هذه التحليلات داخل المنشور.
- إذا كانت بيانات SERP أو نتائج البحث متاحة داخل حزمة المصادر، استخرج الأسئلة المتكررة والفجوات التي لم تجب عنها النتائج، وغطِّ فجوة مفيدة واحدة على الأقل. لا تدّعِ إجراء SERP review إذا لم تتوفر بيانات بحث فعلية.
- لا تخترع حجم بحث أو ترتيبًا أو منافسين أو أسئلة منسوبة إلى Google. إذا لم تتوفر بيانات SERP، استخدم صياغة السؤال الطبيعي ونية البحث فقط.
- حدّد إجابة مباشرة للسؤال الأساسي في أول 2-3 جمل، ثم أضف الشروط والاستثناءات والخطوة العملية ذات الصلة.
- اجعل المنشور قابلًا للاقتباس في نتائج البحث والإجابات الآلية: إجابة واضحة، مصطلحات قانونية صحيحة، تحديد مصر عند الحاجة، وشرح مستقل لا يعتمد على سياق سابق.
- لا تحوّل منشور Facebook إلى مقال SEO أو مذكرة قانونية. استخدم فقرة قصيرة أو 3 نقاط كحد أقصى عندما تفيد، وابتعد عن التكرار والحشو.
- اكتب Facebook بعربية مصرية سليمة؛ ممنوع خلط العربية بكلمات إنجليزية عشوائية أو أخطاء إملائية أو كلمات مكسورة. استخدم المصطلح الإنجليزي فقط إذا كان شائعًا وضروريًا، مع شرحه بالعربية.
- راجع كل جملة لغويًا: توافق الفعل والفاعل، سلامة الضمائر، علامات الترقيم، وعدم تكرار المعنى. احذف أي عبارة غير مفهومة بدل تمريرها.
- لا تنسب للقرار الإداري أو القانون أو المحكمة أثرًا غير ثابت. لا تقل إن الميعاد يتجدد أو يتوقف أو توجد مهلة أقصر إلا إذا أثبت المصدر ذلك تحديدًا.
- عند ذكر ميعاد أو رقم مادة أو إجراء، اذكر نقطة بدء الحساب والاستثناءات المؤثرة إذا كانت ثابتة بالمصادر. لا تختزل القاعدة بما يغير معناها.
- قبل إخراج JSON، نفّذ مراجعة نهائية صامتة: (1) هل أجاب أول النص عن سؤال الباحث؟ (2) هل كل معلومة قانونية مسندة؟ (3) هل النص مصري سليم ومفهوم؟ (4) هل توجد كلمة دخيلة أو جملة مبتورة؟ (5) هل CTA طبيعية وغير مضللة؟ أصلح أي خلل قبل الإخراج.

أعد JSON فقط بهذا الشكل:
{
  "post": "...",
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
    # The core model now produces legal copy only. Image scene descriptions are
    # generated separately by the auxiliary-task router.
    for field in ("post", "review_level", "review_flags", "legal_sources_used", "hook_pattern"):
        if field not in data:
            raise RuntimeError(f"Gemini JSON is missing required field: {field}")
    data["image_mode"] = "CONTEXT_ONLY"
    data["review_level"] = _normalize_review_level(data.get("review_level"))
    data["review_flags"] = _normalize_list(data.get("review_flags"))
    data["legal_sources_used"] = _normalize_list(data.get("legal_sources_used"))
    allowed_hooks = {"question","incident","surprise_fact","common_mistake","practical_scenario","client_problem","legal_rule","contrast","narrative","conclusion_first"}
    data["hook_pattern"] = str(data.get("hook_pattern", "")).strip().lower()
    if data["hook_pattern"] not in allowed_hooks:
        raise RuntimeError("Gemini returned an invalid hook_pattern.")
    data["post"] = str(data.get("post", "")).strip()
    data["image_brief"] = ""
    if not data["post"]:
        raise RuntimeError("Gemini returned an empty post.")
    return data


def _generate_once(client: Any, selected_model: str, prompt: str) -> dict[str, Any]:
    response = client.models.generate_content(
        model=selected_model,
        contents=SYSTEM_PROMPT + "\n\n" + prompt,
        # Ask Gemini and OpenAI-compatible fallback providers for constrained JSON.
        # The router maps response_mime_type to JSON-object mode for compatible APIs.
        config={
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
            "temperature": 0.25,
        },
    )
    raw_text = (getattr(response, "text", None) or "").strip()
    if not raw_text:
        raise RuntimeError("Gemini returned an empty response.")
    return _validate_data(_extract_json(raw_text))



def _deterministic_legal_scene(topic: str, post: str) -> str | None:
    """Return a stable, non-fictional visual brief for abstract legal checklist topics."""
    source = " ".join(f"{topic or ''} {post or ''}".casefold().split())
    criminal_contribution = "المساهمة الجنائية" in source or "criminal contribution" in source
    checklist_angle = any(term in source for term in (
        "checklist", "check list", "قائمة مراجعة", "قبل بدء أي إجراء",
        "قبل اتخاذ أي إجراء", "قبل البدء في الإجراءات",
    ))
    if not (criminal_contribution and checklist_angle):
        return None
    return (
        "Photorealistic overhead still-life photograph, tightly framed on a modern "
        "law-office desk. The image must communicate a practical pre-action checklist "
        "for criminal participation: one large blank checklist page with a short column "
        "of empty square boxes, beside three small distinct neutral metal markers "
        "connected by thin lines to represent separate legal roles in one case. Include "
        "one closed navy case folder and one black pen. The checklist page and three "
        "connected role markers are the unmistakable main subject and fill most of the "
        "image. Contemporary, restrained navy, ivory and muted-gold palette; clean "
        "professional editorial photography; soft natural side lighting; simple "
        "uncluttered composition. Absolutely no people, human figures, faces, hands, "
        "newspapers, magazines, courtroom, police, judge, scales, gavel, extra props, "
        "collage, panels, symbols resembling letters, or text of any kind. All paper "
        "surfaces must be completely blank apart from the empty checkbox outlines. "
        "Use the requested output aspect ratio exactly; do not add borders or crop "
        "the checklist or role markers. Illustrative still life only, not real evidence."
    )

def generate_image_scene_from_post(api_key: str, model: str, post: str, topic: str = "") -> str:
    """Derive one concrete visual scene from the final post, using stable briefs for abstract legal angles."""
    post = " ".join(str(post or "").split()).strip()
    if not post:
        raise RuntimeError("Final post content is required.")
    deterministic_scene = _deterministic_legal_scene(topic, post)
    if deterministic_scene:
        return deterministic_scene
    if not api_key and not has_any_provider_key():
        raise RuntimeError("No text AI provider is configured. Set GEMINI_API_KEY or a fallback provider key.")
    selected_model = (model or DEFAULT_TEXT_MODEL).strip().removeprefix("models/") or DEFAULT_TEXT_MODEL
    client = create_client(api_key=api_key, task="image_description")
    prompt = f"""
Transform the FINAL POST below into one concrete, image-ready scene description.

STRICT RULES:
- The final post is the ONLY semantic source.
- Identify the main subject and at least ONE concrete visual element connected to any meaningful part of the post.
- For abstract legal explanations, choose the simplest recognizable everyday object, setting, action, or document that reasonably relates to the topic.
- The scene may illustrate only ONE aspect of the topic; it does not need to explain the entire legal doctrine or reproduce every detail.
- Prefer a clear, ordinary, topic-related scene over a complicated or overly literal composition.
- Do not force a courtroom, lawyer, scales, police scene, contract, or any stock legal symbol when it is not relevant.
- Use a contemporary everyday setting. Keep the image understandable and visually clean; a partial but genuine topic connection is sufficient.
- Never invent people, actions, documents, locations, events, numbers, logos, or facts.
- Use one scene only, not a collage or multiple panels.
- Describe subject, action, setting, important visual evidence, composition, camera angle, and lighting.
- English only.
- No readable text, letters, numbers, logos, captions, watermarks, UI, or infographic elements in the image.

FINAL POST:
{post}

Return only the English visual scene description.
"""
    import time
    last_error = None
    response = None
    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=selected_model,
                contents=prompt,
                config={"max_output_tokens": 1200},
            )
            break
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                delay = attempt * 2
                print(f"Image scene request failed; retry {attempt + 1}/3 in {delay}s: {exc}")
                time.sleep(delay)
    if response is None:
        raise RuntimeError(f"Image scene generation failed after 3 attempts: {last_error}") from last_error
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
    if not api_key and not has_any_provider_key():
        raise RuntimeError("No text AI provider is configured. Set GEMINI_API_KEY or a fallback provider key.")
    topic = (topic or "").strip()
    if not topic:
        raise RuntimeError("Topic is empty.")
    selected_model = (model or DEFAULT_TEXT_MODEL).strip().removeprefix("models/") or DEFAULT_TEXT_MODEL
    client = create_client(api_key=api_key)

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
لا تكتب وصف صورة أو image_brief أو أي حقول إضافية؛ مهمة الصور منفصلة تمامًا عن هذه المهمة.
"""

    retry_prompt = base_prompt + """

مراجعة جودة قبل الإخراج:
أخرج JSON صالحًا فقط، بلا Markdown أو أسوار كود أو أي نص قبله أو بعده.
التزم بالمفاتيح الخمسة المحددة في عقد الإخراج، ولا تضف أي مفتاح آخر.
اكتب منشورًا مكتملًا ومتماسكًا في 180 إلى 260 كلمة، ولا تبدأ جملة لا تستطيع إكمالها.
إذا اقتربت من حد الإخراج، اختصر الشرح بدل قطع JSON أو ترك جملة ناقصة.
لا تكتب وصف صورة أو image_brief.
"""

    last_error: Exception | None = None
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        try:
            if attempt == 1:
                attempt_prompt = base_prompt
            elif attempt == 2:
                attempt_prompt = retry_prompt
            else:
                # Recovery prompt is deliberately shorter to reduce truncation risk.
                attempt_prompt = base_prompt + """

إعادة إخراج إلزامية بسبب فشل الاستجابة السابقة:
- أعد JSON صالحًا فقط بالمفاتيح الخمسة المطلوبة دون أي نص خارجي.
- اجعل post بين 180 و240 كلمة، مكتملًا حتى آخر حرف.
- لا تكتب image_brief أو image_mode أو أي حقول إضافية.
- لا تضحِّ بالدقة القانونية، واحذف التفاصيل غير المتحقق منها بدل اختلاقها.
- لا تبدأ جملة أو فقرة لا تستطيع إكمالها.
"""
            data = _generate_once(client, selected_model, attempt_prompt)
            if _post_quality_ok(data["post"]) and _soft_cta_present(data["post"]):
                return data
            if _post_quality_ok(data["post"]):
                data["post"] = data["post"].rstrip() + "\n\nوالتفاصيل والوقائع والمستندات قد تغيّر التقييم القانوني، لذلك مراجعة الموقف قبل اتخاذ قرار مهم قد تكون فارقة."
                if _post_quality_ok(data["post"]):
                    return data
            last_error = RuntimeError("Gemini returned content below the pre-editorial quality threshold.")
        except Exception as exc:
            last_error = exc
            print(f"Legal draft generation attempt {attempt}/{MAX_GENERATION_ATTEMPTS} failed: {exc}")
    raise RuntimeError(f"Gemini content generation failed after {MAX_GENERATION_ATTEMPTS} attempts: {last_error}")
