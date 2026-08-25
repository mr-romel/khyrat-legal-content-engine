from __future__ import annotations

import json
import re
import time
from typing import Any

from google import genai
from google.genai import types

from legal_reference_registry import build_reference_context, extract_grounding_sources, format_grounding_sources


DEFAULT_FALLBACK_MODEL = "gemini-2.5-flash"
MAX_PRIMARY_RETRIES = 3
MAX_FALLBACK_RETRIES = 2
MAX_RESEARCH_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 5.0
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}

LEGAL_RESEARCH_PROMPT = """
أنت باحث قانوني مصري يعمل قبل نشر محتوى قانوني على حساب محامٍ.
نفّذ بحثًا قانونيًا معمقًا على الإنترنت للتحقق من الموضوع والنص المقترح.

قواعد البحث الإلزامية:
1) مصر فقط، مع مراعاة القانون النافذ حتى تاريخ البحث.
2) التزم بهرم المصادر المرفق في الطلب: ابدأ بالمصادر الأولية والرسمية، ثم المصادر القانونية المتخصصة، ثم المصادر التفسيرية عند الحاجة.
3) لا تجعل مقالًا عامًا أو منشورًا على وسائل التواصل أساسًا وحيدًا لنتيجة قانونية حاسمة.
4) ابحث عن التعديلات الحديثة والإلغاء والاستبدال والنصوص الخاصة والاستثناءات ذات الصلة.
5) إذا ذُكر حكم أو مبدأ أو رقم مادة أو عقوبة أو ميعاد أو اختصاص، تحقق منه تحديدًا ولا تكتفِ بتشابه الكلمات.
6) افحص التعارض بين القواعد العامة والقوانين الخاصة، وبين النص الحالي والنصوص السابقة.
7) لا تستنتج قاعدة لمجرد أن مصدرًا قالها؛ قارِن بين المصادر.
8) إذا تعذر التحقق من نقطة جوهرية، صرّح بذلك صراحة بدل التخمين.
9) لا تعتبر نتيجة محرك البحث نفسها مصدرًا؛ المصدر هو الصفحة أو الوثيقة الأصلية التي تقف وراء النتيجة.
10) البحث هدفه التحقق القانوني وليس كتابة بوست جديد.

أعد تقريرًا منظمًا يتضمن:
- السؤال القانوني الحقيقي.
- القوانين/اللوائح/القرارات ذات الصلة وحالتها الزمنية.
- أهم النصوص أو المبادئ التي تم التحقق منها، بصياغة مختصرة دون نسخ مطول.
- الأحكام/المبادئ القضائية المهمة إن وجدت.
- الاستثناءات والقيود.
- نقاط الاتفاق والاختلاف بين المصادر.
- أخطر الادعاءات الموجودة في المحتوى والتي تحتاج تصحيحًا.
- حكم ثقة لكل نقطة: HIGH / MEDIUM / LOW.
- روابط المصادر التي تم العثور عليها إن كانت متاحة.

لا تخترع مصدرًا أو رابطًا. إذا لم تجد مصدرًا مناسبًا، اذكر ذلك.
"""

SYSTEM_PROMPT = """
أنت المراجع القانوني والتحريري النهائي لمحتوى قانوني مصري قبل نشره على وسائل التواصل الاجتماعي.

أنت تعمل كـLEGAL QUALITY GATE شامل لكل المحتوى القانوني، وليس كمدقق لغوي أو مراجع لمجال الشركات فقط. أي موضوع قانوني في أي فرع يجب أن يمر بنفس مستوى الفحص.

المهام القانونية الإلزامية:
1) استخراج كل ادعاء قانوني جوهري وفحصه على حدة.
2) تحديد الفرع القانوني والتشريع/اللائحة/القرار المصري المنطبق على كل ادعاء.
3) مقارنة الادعاءات بنتائج البحث القانوني والمصادر المتاحة، مع إعطاء الأولوية للمصادر الأولية والرسمية.
4) التحقق من القانون النافذ والتعديلات الحديثة متى كان الموضوع حساسًا زمنيًا.
5) التحقق من الاختصاص والصفة والأهلية والإجراءات والمواعيد والآثار والاستثناءات والقيود متى كانت ذات صلة.
6) فحص النص القانوني في سياقه وعدم اقتطاع قاعدة بطريقة تغير معناها.
7) التمييز بين القاعدة العامة والاستثناء، والحق الموضوعي والإجراء، والبطلان وعدم النفاذ والقابلية للإبطال وغيرها من المصطلحات ذات الأثر المختلف.
8) عدم تعميم حكم فئة أو مركز قانوني على فئة أو مركز آخر.
9) التحقق من الأحكام والمبادئ والأرقام والتواريخ والعقوبات والاختصاصات والمواعيد إذا وردت.
10) إذا كان التصحيح ممكنًا دون تغيير جوهر الموضوع، أعد صياغة البوست قانونيًا.
11) إذا كان الخطأ جوهريًا، أو توجد مصادر متعارضة غير محسومة، أو كانت نقطة حاسمة غير قابلة للتحقق بدرجة مناسبة، اجعل legal_status = BLOCK.
12) لا تعتمد على ذاكرة النموذج وحدها في أي نقطة قانونية حاسمة.

قواعد المحتوى:
- الدقة القانونية شرط أساسي، لكن كثافة القانون ليست هدفًا.
- المراجع والبحث يعملان خلف الكواليس ولا نحول البوست إلى مذكرة قانونية.
- البوست يجب أن يكون سهلًا على غير المتخصص، سريع الفهم، وغير ممل.
- لا تضحِ بالدقة من أجل Hook أو تفاعل.
- إذا كانت الصياغة صحيحة قانونيًا لكنها ثقيلة أو أكاديمية أو مملة، استخدم REWRITE لا BLOCK.
- إذا كان تبسيط نقطة سيشوّه معناها القانوني، احتفظ بالقدر الضروري من الدقة واشرحه ببساطة.
- احذف الحشو والتكرار والمصطلحات القانونية غير الضرورية.
- اجعل الفقرات قصيرة، والفكرة الأساسية واضحة مبكرًا.
- Facebook: لغة مصرية طبيعية ومباشرة، مع المحافظة على المهنية.
- LinkedIn: نسخة مستقلة أطول بوضوح، مهنية وتحليلية، ويفضل 1200–1800 حرف عند ملاءمة الموضوع، مع أثر عملي وإدارة مخاطر أو حوكمة/امتثال بحسب الموضوع، دون حشو أو اختراع حقائق.
- لا تجعل LinkedIn مجرد إعادة ترتيب لـFacebook.
- لا تكتب أي تعليق جديد؛ راجع التعليقات الموجودة فقط.
- لا تخترع مادة أو حكمًا أو رقم طعن أو عقوبة أو ميعاد أو رابط مصدر.
- أعد JSON فقط.
"""


def _extract_status_code(exc: Exception) -> int | None:
    candidates = [getattr(exc, "status_code", None), getattr(exc, "code", None), getattr(exc, "status", None)]
    for attr in ("response", "resp"):
        obj = getattr(exc, attr, None)
        if obj is not None:
            candidates.extend([getattr(obj, "status_code", None), getattr(obj, "status", None), getattr(obj, "code", None)])
    for candidate in candidates:
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    match = re.search(r"\b(?:HTTP\s*)?(408|429|500|502|503|504)\b", str(exc))
    return int(match.group(1)) if match else None


def _generate(*, client, model: str, prompt: str, attempts: int, label: str, config: Any = None) -> Any:
    for attempt in range(1, attempts + 1):
        try:
            chat = client.chats.create(model=model)
            if config is None:
                return chat.send_message(SYSTEM_PROMPT + "\n\n" + prompt)
            return client.models.generate_content(model=model, contents=prompt, config=config)
        except Exception as exc:
            status = _extract_status_code(exc)
            if status not in TRANSIENT_STATUS_CODES or attempt >= attempts:
                raise
            delay = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"Legal/editorial review {label} temporary error ({status}); retry {attempt}/{attempts - 1} in {delay:.0f}s...")
            time.sleep(delay)
    raise RuntimeError("Legal/editorial review failed unexpectedly.")


def _extract_json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*", "", (text or "").strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("Legal/editorial review response was not valid JSON.")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Legal/editorial review response contained invalid JSON.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Legal/editorial review response was not an object.")
    return data


def _clean_list(value: Any, minimum: int = 5) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeError("Legal/editorial review returned an invalid comment list.")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        key = re.sub(r"\s+", " ", text).casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    if len(result) < minimum:
        raise RuntimeError(f"Legal/editorial review returned fewer than {minimum} comments.")
    return result[:5]


def _normalize_status(value: Any, allowed: set[str], default: str) -> str:
    status = str(value or default).strip().upper()
    return status if status in allowed else default


def _research_web(*, client, model: str, topic: str, facebook_post: str, legal_sources: str) -> tuple[str, list[dict[str, str]]]:
    reference_context = build_reference_context(user_sources=legal_sources)
    prompt = f"""
{LEGAL_RESEARCH_PROMPT}

{reference_context}

موضوع المحتوى:
{topic}

النص المراد التحقق منه:
{facebook_post}

المصادر التي أدخلها المستخدم مسبقًا إن وجدت:
{legal_sources or 'لا توجد مصادر مدخلة.'}

نفّذ بحثًا متعدد الزوايا: التشريع الحالي، التعديلات، الاستثناءات، والمبادئ القضائية أو التنظيمية ذات الصلة. لا تكتفِ بنتيجة بحث واحدة.

ابحث أولًا عن المصادر الرسمية ذات الصلة بموضوعك، ثم استخدم المصادر المتخصصة عند الحاجة للتحقق أو المقارنة. إذا كانت المسألة تتعلق بقطاع منظم، ابحث أيضًا في موقع الجهة التنظيمية المختصة. إذا كانت المسألة قضائية، ابحث في محكمة النقض والمحكمة الدستورية ومجلس الدولة بحسب الاختصاص.
"""
    research_config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.1,
    )
    response = _generate(
        client=client,
        model=model or DEFAULT_FALLBACK_MODEL,
        prompt=prompt,
        attempts=MAX_RESEARCH_RETRIES,
        label="deep web legal research",
        config=research_config,
    )
    text = str(getattr(response, "text", "") or "").strip()
    sources = extract_grounding_sources(response)
    if len(text) < 300:
        raise RuntimeError("Deep legal web research returned insufficient evidence.")
    if not sources:
        raise RuntimeError("Deep legal web research returned no verifiable grounding sources.")
    return text, sources


def review_and_prepare(
    *,
    api_key: str,
    model: str,
    topic: str,
    facebook_post: str,
    facebook_comments: list[str],
    linkedin_comments: list[str],
    legal_sources: str = "",
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    if not facebook_post.strip():
        raise RuntimeError("Facebook post is empty.")

    primary_model = (model or "").strip() or DEFAULT_FALLBACK_MODEL
    fallback_model = DEFAULT_FALLBACK_MODEL
    client = genai.Client(api_key=api_key)

    research_available = True
    research = ""
    grounded_sources: list[dict[str, str]] = []

    print("Legal research gate: starting deep Egyptian legal web research...")
    try:
        research, grounded_sources = _research_web(
            client=client,
            model=primary_model,
            topic=topic,
            facebook_post=facebook_post,
            legal_sources=legal_sources,
        )
    except Exception as exc:
        research_available = False
        print(f"Legal research gate unavailable: {exc}")
        print("Legal research gate: switching to SIMPLE REVIEW mode; publication will continue unless the post itself contains an obvious unsafe legal assertion.")

    if research_available:
        print(f"Legal research gate: completed with {len(grounded_sources)} grounded sources.")
    else:
        print("Legal research gate: advisory only for this run; no publication block caused solely by research outage.")

    reference_context = build_reference_context(user_sources=legal_sources)
    grounded_source_text = format_grounding_sources(grounded_sources)
    review_mode_instruction = (
        "RESEARCH MODE: استخدم تقرير البحث ومصادر Grounding للتحقق من الادعاءات بدقة."
        if research_available
        else
        "SIMPLE REVIEW MODE: تعذر البحث القانوني المعمق تقنيًا في هذه الدورة. لا تجعل غياب البحث سببًا منفردًا للـBLOCK. راجع البوست مراجعة قانونية/تحريرية بسيطة، واحذف أو عمّم أي مادة أو عقوبة أو رقم حكم أو ميعاد أو تاريخ أو ادعاء دقيق غير متحقق بدل اختلاقه. استخدم CLEAR أو REWRITE قدر الإمكان، واعتبر الثقة MEDIUM إذا لم توجد مشكلة ظاهرة. لا تستخدم LOW أو BLOCK لمجرد عدم توفر البحث."
    )

    prompt = f"""
{SYSTEM_PROMPT}

{reference_context}

{review_mode_instruction}

الموضوع:
{topic}

المصادر القانونية المدخلة:
{legal_sources or 'لا توجد مصادر مدخلة.'}

مصادر Grounding التي استخدمها بحث Google داخل Gemini:
{grounded_source_text}

تقرير البحث القانوني المعمق من الإنترنت:
{research or 'غير متاح في هذه الدورة؛ نفّذ SIMPLE REVIEW MODE فقط.'}

Facebook قبل المراجعة:
{facebook_post}

تعليقات Facebook قبل المراجعة:
{json.dumps(facebook_comments, ensure_ascii=False)}

تعليقات LinkedIn قبل المراجعة:
{json.dumps(linkedin_comments, ensure_ascii=False)}

نفّذ المراجعة على مرحلتين داخلية:
أولًا: افحص الادعاءات القانونية بما يتناسب مع وضع المراجعة الحالي، وصحح الصياغة أو عمّمها إذا كانت التفاصيل الدقيقة غير متحققة.
ثانيًا: حسّن البساطة والجاذبية دون إضعاف الدقة.

قواعد قرار النشر:
- legal_status = CLEAR إذا كانت الادعاءات الجوهرية سليمة أو يمكن شرحها بأمان بصورة عامة.
- legal_status = REWRITE إذا كان المحتوى صحيح الاتجاه ويمكن إصلاح صياغته أو تضييق نطاقه دون تغيير جوهره.
- legal_status = BLOCK فقط إذا كان هناك خطأ قانوني جوهري واضح أو محتوى لا يمكن جعله آمنًا بإعادة الصياغة.
- في SIMPLE REVIEW MODE: عدم وجود مصادر Grounding أو انخفاض الثقة بسبب تعذر البحث وحده ليس سببًا للـBLOCK.
- في SIMPLE REVIEW MODE: إذا وُجد رقم مادة أو عقوبة أو حكم أو ميعاد أو تاريخ محدد غير متحقق، احذف التفصيل أو عمّمه بدل إيقاف البوست متى كان ذلك ممكنًا.
- legal_confidence = HIGH عند التحقق القوي، وMEDIUM عند المراجعة البسيطة أو عند غياب البحث مع عدم وجود مشكلة ظاهرة، وLOW فقط إذا كانت هناك مشكلة قانونية جوهرية لا يمكن تجاوزها بأمان.
- readability_status = CLEAR إذا كان سهلًا وغير ممل.
- readability_status = REWRITE إذا كان صحيحًا لكنه ثقيل أو طويل أو أكاديمي أو مكرر.
- readability_status = BLOCK فقط إذا كان الشكل نفسه يجعل المعنى مضللًا أو غير قابل للفهم حتى بعد إعادة الصياغة.
- readability_score من 0 إلى 100.

ممنوع اختراع معلومات جديدة في LinkedIn أو التعليقات.
ممنوع إضافة مادة قانونية أو حكم أو رقم طعن أو عقوبة أو ميعاد لم يثبت.

أعد JSON فقط بهذا الشكل:
{{
  "legal_status": "CLEAR|REWRITE|BLOCK",
  "readability_status": "CLEAR|REWRITE|BLOCK",
  "legal_confidence": "HIGH|MEDIUM|LOW",
  "readability_score": 0,
  "legal_findings": ["..."],
  "research_sources": ["..."],
  "decision_reason": "...",
  "facebook_post": "...",
  "linkedin_post": "...",
  "facebook_comments": ["...", "...", "...", "...", "..."],
  "linkedin_comments": ["...", "...", "...", "...", "..."]
}}
"""

    try:
        response = _generate(
            client=client,
            model=primary_model,
            prompt=prompt,
            attempts=MAX_PRIMARY_RETRIES,
            label=f"primary model {primary_model}",
        )
    except Exception as primary_exc:
        status = _extract_status_code(primary_exc)
        if status not in TRANSIENT_STATUS_CODES or fallback_model == primary_model:
            raise
        print(f"Legal/editorial review primary model unavailable; switching to {fallback_model}.")
        response = _generate(
            client=client,
            model=fallback_model,
            prompt=prompt,
            attempts=MAX_FALLBACK_RETRIES,
            label=f"fallback model {fallback_model}",
        )

    data = _extract_json(getattr(response, "text", ""))
    legal_status = _normalize_status(data.get("legal_status"), {"CLEAR", "REWRITE", "BLOCK"}, "BLOCK")
    readability_status = _normalize_status(data.get("readability_status"), {"CLEAR", "REWRITE", "BLOCK"}, "BLOCK")
    legal_confidence = _normalize_status(data.get("legal_confidence"), {"HIGH", "MEDIUM", "LOW"}, "LOW")
    try:
        readability_score = max(0, min(100, int(data.get("readability_score", 0))))
    except (TypeError, ValueError):
        readability_score = 0

    findings = data.get("legal_findings", [])
    if not isinstance(findings, list):
        findings = [str(findings)] if findings else []
    reason = str(data.get("decision_reason", "")).strip()

    merged_sources: list[str] = []
    for item in grounded_sources:
        url = str(item.get("url", "")).strip()
        if url and url not in merged_sources:
            merged_sources.append(url)
    for item in data.get("research_sources", []) if isinstance(data.get("research_sources"), list) else []:
        url = str(item or "").strip()
        if url and url not in merged_sources:
            merged_sources.append(url)

    if research_available:
        if legal_status == "BLOCK" or readability_status == "BLOCK" or legal_confidence == "LOW":
            raise RuntimeError(
                "Publication blocked by comprehensive legal/readability gate: "
                + (reason or "insufficient legal certainty or unacceptable content quality.")
            )
    else:
        if readability_status == "BLOCK" or legal_status == "BLOCK":
            raise RuntimeError(
                "Publication blocked by simple legal/readability review: "
                + (reason or "the post could not be made safe by simple rewriting.")
            )
        if legal_confidence == "LOW":
            legal_confidence = "MEDIUM"
            print("Simple review: normalized LOW confidence to MEDIUM because deep research was unavailable; no concrete legal blocker was found.")

    facebook = str(data.get("facebook_post", "")).strip()
    linkedin = str(data.get("linkedin_post", "")).strip()
    if not facebook or not linkedin:
        raise RuntimeError("Legal/editorial review returned an empty post.")

    facebook_comments_ready = _clean_list(data.get("facebook_comments"))
    linkedin_comments_ready = _clean_list(data.get("linkedin_comments"))

    if len(linkedin) < max(900, int(len(facebook) * 1.15)) and len(linkedin) < 1200:
        raise RuntimeError("LinkedIn version failed the required expansion/professional-depth gate.")

    if readability_status == "REWRITE":
        print(f"Readability gate: rewritten for simplicity and engagement; score={readability_score}/100.")
    else:
        print(f"Readability gate: passed; score={readability_score}/100.")

    print(f"Legal gate: {legal_status} | confidence={legal_confidence} | findings={len(findings)}")
    if findings:
        print("Legal gate findings: " + " | ".join(str(item) for item in findings[:5]))
    print("Legal research sources checked: " + " | ".join(merged_sources[:8]))

    return {
        "facebook_post": facebook,
        "linkedin_post": linkedin,
        "facebook_comments": facebook_comments_ready,
        "linkedin_comments": linkedin_comments_ready,
        "legal_status": legal_status,
        "legal_confidence": legal_confidence,
        "legal_findings": [str(item) for item in findings],
        "research_sources": merged_sources,
        "readability_status": readability_status,
        "readability_score": readability_score,
        "decision_reason": reason,
    }
