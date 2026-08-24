from __future__ import annotations

import json
import re
import time
from typing import Any

from google import genai


DEFAULT_FALLBACK_MODEL = "gemini-2.5-flash"
MAX_PRIMARY_RETRIES = 3
MAX_FALLBACK_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 5.0
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}

SYSTEM_PROMPT = """
أنت المراجع القانوني والتحريري النهائي لمحتوى قانوني مصري قبل نشره على وسائل التواصل الاجتماعي.

أنت تعمل كـLEGAL QUALITY GATE شامل لكل المحتوى القانوني، وليس كمدقق لغوي أو مراجع لمجال الشركات فقط. أي موضوع قانوني في أي فرع أو مجال يجب أن يمر بنفس مستوى الفحص قبل النشر.

نطاق المراجعة يشمل — دون حصر — المدني، التجاري، الشركات، العمل، الإداري، الجنائي، الأسرة، الأحوال الشخصية، المرافعات، الإثبات، العقود، الملكية الفكرية، الضرائب، التأمينات، الإيجارات، العقارات، البنوك، الاستثمار، التأمين، الطبي، المسؤولية المهنية، حماية المستهلك، المرور، الجرائم الإلكترونية، الإجراءات الجنائية، التنفيذ، الإفلاس وإعادة الهيكلة، وأي تشريع أو لائحة أو نظام قانوني مصري آخر يتناوله المحتوى.

المهام الإلزامية:
1) استخراج كل ادعاء قانوني جوهري في المحتوى وفحصه على حدة.
2) تحديد الفرع القانوني والتشريع/اللائحة/القرار أو النظام المصري المنطبق على كل ادعاء، وعدم الاكتفاء بالتشابه العام بين القواعد.
3) التحقق من الاختصاص والصفة والأهلية والإجراءات والمواعيد والآثار القانونية والاستثناءات والقيود متى كانت ذات صلة.
4) فحص النص القانوني في سياقه، وعدم اقتطاع قاعدة من مادة أو حكم بطريقة تغيّر معناها.
5) التمييز بين القاعدة العامة والاستثناء، وبين الحق الموضوعي والإجراء، وبين صحة التصرف وبطلانه وقابليته للإبطال وعدم نفاذه، وبين الحكم القانوني والرأي الفقهي أو الممارسة العملية.
6) فحص مدى انطباق القانون على الوقائع المفترضة وعدم إدخال وقائع غير مذكورة.
7) فحص المصطلحات القانونية بدقة وعدم استخدام مصطلحين متقاربين وكأنهما مترادفان إذا كان بينهما أثر قانوني مختلف.
8) فحص العلاقة بين القوانين الخاصة والقواعد العامة، وأي تعارض أو تخصيص أو استثناء ظاهر من المعطيات المتاحة.
9) فحص الأحكام والمبادئ القضائية والأرقام والتواريخ والعقوبات والاختصاصات والمواعيد إذا وردت، وعدم اختلاق أي منها.
10) إذا ذُكرت أكثر من فئة أو كيان أو مركز قانوني، افحص الحكم لكل فئة على حدة ولا تعمم حكم فئة على أخرى.
11) إذا كان المحتوى قابلًا للتصحيح دون تغيير جوهر الموضوع، أعد صياغته قانونيًا بشكل صحيح.
12) إذا كان الخطأ جوهريًا، أو تعارضت المعطيات، أو كانت نقطة قانونية حاسمة غير قابلة للتحقق بدرجة ثقة مناسبة من المصادر والمعطيات المتاحة، امنع النشر تمامًا.
13) بعد اجتياز المراجعة القانونية، نفّذ المراجعة اللغوية والتحريرية.
14) أنشئ نسخة LinkedIn أطول بوضوح من Facebook، وليست مجرد اختصار أو إعادة ترتيب؛ تستهدف الجمهور المهني وتضيف تحليلًا عمليًا وإدارة مخاطر وحوكمة أو امتثال متى كان ذلك مناسبًا، من غير اختراع أي حقيقة قانونية جديدة.
15) راجع جميع التعليقات لغويًا مع الحفاظ على طبيعتها وعدم تحويلها إلى لغة رسمية متكلفة.

قواعد قانونية صارمة:
- البيئة القانونية: جمهورية مصر العربية فقط.
- لا تفترض أن معلومة عامة أو قاعدة مشهورة صحيحة في كل الأحوال؛ اربط كل نتيجة بنطاقها القانوني.
- لا تفترض أن قاعدة تخص نوع كيان أو عقد أو دعوى أو إجراء تنطبق على نوع آخر.
- إذا اختلف الحكم بحسب الوقائع أو الصفة أو نوع الكيان أو نوع الدعوى أو المرحلة الإجرائية، يجب بيان ذلك أو تضييق نطاق البوست.
- لا تعتبر منصبًا أو صفةً وحدها دليلًا على الاختصاص؛ افحص مصدر الاختصاص.
- لا تستخدم "يحق" أو "لا يجوز" أو "يلزم" أو "يُعاقب" أو أي عبارة قطعية إلا إذا كانت النتيجة مبررة بنطاقها الصحيح.
- لا تخترع مادة أو حكمًا أو رقم طعن أو غرامة أو عقوبة أو ميعادًا أو جهة اختصاص أو رابط مصدر.
- وجود مصدر مدخل لا يعني صحة الاستنتاج؛ افحص مدى دعمه لكل نتيجة جوهرية.
- إذا كانت المصادر المدخلة غير كافية للتحقق من نقطة جوهرية، لا تخمّن. استخدم BLOCK.
- لا تعتبر المعلومة الناتجة عن الذاكرة العامة للنموذج مصدرًا موثوقًا وحدها في النقاط القانونية الحاسمة.
- لا تمرر خطأ قانونيًا جوهريًا باعتباره مشكلة أسلوب.
- لا تغير النتيجة القانونية لمجرد جعل النص أكثر جاذبية.
- لا تضف استثناءات أو تفاصيل غير متحققة.
- إذا كان الموضوع يحتاج تحديد قانون نافذ أو تعديل تشريعي حديث أو حكم قضائي محدد ولم تتوفر مصادر كافية للتحقق، استخدم BLOCK بدل التخمين.
- إذا احتوى المحتوى على أكثر من فرع قانوني، راجع كل فرع على حدة ثم راجع الاتساق بينهم.
- حافظ على صوت Facebook الطبيعي والمصري دون التضحية بالدقة.
- LinkedIn يكون أكثر مهنية وتحليلًا، ويفضل أن يكون تقريبًا 1200–1800 حرفًا عند ملاءمة الموضوع، مع تجنب الحشو.
- لا تكتب أي تعليق جديد من عندك؛ راجع التعليقات الموجودة فقط.
- أعد JSON فقط.
"""


def _extract_status_code(exc: Exception) -> int | None:
    candidates = [
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
        getattr(exc, "status", None),
    ]
    for attr in ("response", "resp"):
        obj = getattr(exc, attr, None)
        if obj is not None:
            candidates.extend(
                [
                    getattr(obj, "status_code", None),
                    getattr(obj, "status", None),
                    getattr(obj, "code", None),
                ]
            )
    for candidate in candidates:
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    match = re.search(r"\b(?:HTTP\s*)?(408|429|500|502|503|504)\b", str(exc))
    return int(match.group(1)) if match else None


def _generate(*, client, model: str, prompt: str, attempts: int, label: str) -> Any:
    for attempt in range(1, attempts + 1):
        try:
            chat = client.chats.create(model=model)
            return chat.send_message(SYSTEM_PROMPT + "\n\n" + prompt)
        except Exception as exc:
            status = _extract_status_code(exc)
            if status not in TRANSIENT_STATUS_CODES or attempt >= attempts:
                raise
            delay = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(
                f"Legal/editorial review {label} temporary error ({status}); "
                f"retry {attempt}/{attempts - 1} in {delay:.0f}s..."
            )
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


def _normalize_legal_status(value: Any) -> str:
    status = str(value or "BLOCK").strip().upper()
    if status not in {"CLEAR", "REWRITE", "BLOCK"}:
        return "BLOCK"
    return status


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

    primary_model = (model or "").strip()
    fallback_model = DEFAULT_FALLBACK_MODEL
    client = genai.Client(api_key=api_key)

    prompt = f"""
الموضوع:
{topic}

المصادر القانونية المتاحة من قاعدة المحتوى:
{legal_sources or "لا توجد مصادر قانونية مدخلة."}

Facebook قبل المراجعة:
{facebook_post}

تعليقات Facebook قبل المراجعة:
{json.dumps(facebook_comments, ensure_ascii=False)}

تعليقات LinkedIn قبل المراجعة:
{json.dumps(linkedin_comments, ensure_ascii=False)}

نفّذ المراجعة على مرحلتين داخل نفس المهمة، مع أولوية مطلقة للدقة القانونية:

أولًا — COMPREHENSIVE LEGAL REVIEW:
- استخرج جميع الادعاءات القانونية الجوهرية، حتى لو كانت ضمنية أو وردت في مثال أو CTA.
- حدّد الفرع القانوني لكل ادعاء، والتشريع أو اللائحة أو النظام المصري المنطبق متى أمكن.
- افحص النصوص القانونية في سياقها، ومدى انطباقها على الوقائع المفترضة، وأي شروط أو استثناءات أو قيود.
- افحص الاختصاص والصفة والأهلية والإجراءات والمواعيد والآثار القانونية متى كانت ذات صلة.
- افحص المصطلحات القانونية والتفرقة بين المفاهيم المتشابهة.
- افحص العلاقة بين القانون الخاص والعام، وأي تخصيص أو استثناء أو شرط مؤثر.
- افحص أي أرقام مواد أو أحكام أو عقوبات أو مواعيد أو جهات اختصاص أو تواريخ أو نسب أو حدود مالية.
- افحص أي ادعاء عن "حق" أو "التزام" أو "بطلان" أو "عدم نفاذ" أو "جريمة" أو "عقوبة" أو "سقوط" أو "تقادم" أو "اختصاص" أو "ميعاد".
- إذا كان هناك أكثر من كيان أو فئة أو مركز قانوني، افحص كل واحد على حدة ولا تعمم.
- افحص المصادر المدخلة ومدى دعمها لكل نتيجة جوهرية.
- إذا كان هناك خطأ قابل للإصلاح دون تغيير جوهر الموضوع، صحح النص قانونيًا.
- إذا كان هناك خطأ جوهري، أو تعارض، أو نقص في معلومة حاسمة، أو عدم قدرة على التحقق بدرجة ثقة مناسبة، اجعل legal_status = BLOCK.
- لا تستخدم التخمين لسد أي فجوة قانونية.

ثانيًا — EDITORIAL/PLATFORM REVIEW:
- Facebook: نسخة واضحة وقوية ومصرية طبيعية، مع أقل تغيير لازم بعد التصحيح القانوني.
- LinkedIn: نسخة أطول بوضوح، تقريبًا 1200–1800 حرفًا عند ملاءمة الموضوع، تتضمن تحليلًا مهنيًا وأثرًا عمليًا ومخاطر وحوكمة/امتثال عند ملاءمة الموضوع، دون إضافة أي حقيقة قانونية غير متحققة.
- لا تجعل LinkedIn مجرد تلخيص لـFacebook.
- صحح التعليقات الموجودة فقط.

أعد JSON بهذا الشكل فقط:
{{
  "legal_status": "CLEAR | REWRITE | BLOCK",
  "legal_summary": "ملخص واضح لما تم فحصه والنتيجة القانونية",
  "legal_issues": ["كل نقطة قانونية جوهرية تم اكتشافها أو التحقق منها"],
  "legal_sources_used": ["المصادر أو القواعد القانونية التي تم الاعتماد عليها، دون اختلاق أرقام أو روابط"],
  "facebook_post": "...",
  "linkedin_post": "...",
  "facebook_comments": ["...", "...", "...", "...", "..."],
  "linkedin_comments": ["...", "...", "...", "...", "..."]
}}

مهم جدًا: إذا لم تستطع التحقق بدرجة ثقة مناسبة من أي قاعدة قانونية جوهرية، لا تخمّن؛ استخدم BLOCK واشرح السبب في legal_summary وlegal_issues.
"""

    try:
        response = _generate(
            client=client,
            model=primary_model,
            prompt=prompt,
            attempts=MAX_PRIMARY_RETRIES,
            label=f"primary model {primary_model or 'default'}",
        )
    except Exception as primary_exc:
        status = _extract_status_code(primary_exc)
        if status not in TRANSIENT_STATUS_CODES or not fallback_model or fallback_model == primary_model:
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
    legal_status = _normalize_legal_status(data.get("legal_status"))
    legal_summary = str(data.get("legal_summary", "")).strip()
    legal_issues = [str(item).strip() for item in data.get("legal_issues", []) if str(item).strip()] if isinstance(data.get("legal_issues", []), list) else []
    legal_sources_used = [str(item).strip() for item in data.get("legal_sources_used", []) if str(item).strip()] if isinstance(data.get("legal_sources_used", []), list) else []

    if legal_status == "BLOCK":
        details = legal_summary or "Legal review blocked publication."
        if legal_issues:
            details += " | " + " | ".join(legal_issues[:8])
        raise RuntimeError(f"LEGAL_REVIEW_BLOCK: {details}")

    facebook_post = str(data.get("facebook_post", "")).strip()
    linkedin_post = str(data.get("linkedin_post", "")).strip()
    if not facebook_post or not linkedin_post:
        raise RuntimeError("Legal/editorial review returned an empty post.")

    facebook = _clean_list(data.get("facebook_comments"))
    linkedin = _clean_list(data.get("linkedin_comments"))

    if len(linkedin_post) < max(900, int(len(facebook_post) * 1.35)):
        raise RuntimeError("LINKEDIN_REVIEW_BLOCK: LinkedIn version is not sufficiently expanded beyond Facebook.")

    print(
        "Legal gate: "
        f"{legal_status}; issues={len(legal_issues)}; sources_checked={len(legal_sources_used)}"
    )
    print(
        "Editorial gate: spelling/grammar review completed; "
        f"LinkedIn professional expansion completed ({len(linkedin_post)} characters)."
    )

    return {
        "facebook_post": facebook_post,
        "linkedin_post": linkedin_post,
        "facebook_comments": facebook,
        "linkedin_comments": linkedin,
        "legal_status": legal_status,
        "legal_summary": legal_summary,
        "legal_issues": legal_issues,
        "legal_sources_used": legal_sources_used,
    }
