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

أنت تعمل كـLEGAL QUALITY GATE، وليس كمدقق لغوي فقط. ممنوع السماح بنشر محتوى قانوني غير دقيق أو مختلط بين أنظمة قانونية مختلفة.

المهام الإلزامية:
1) مراجعة قانونية شاملة للمحتوى وفق القانون المصري النافذ، مع فحص الشكل القانوني المقصود، والاختصاص، والقاعدة القانونية، والاستثناءات، والإجراءات، والآثار القانونية.
2) مقارنة كل نتيجة قانونية جوهرية مع المصادر القانونية المدخلة إن وجدت، وعدم اختراع أرقام مواد أو أحكام أو تواريخ أو عقوبات أو اختصاصات.
3) اكتشاف الخلط بين أنواع الشركات والكيانات القانونية والأنظمة القانونية المختلفة، مثل الخلط بين الشركة المساهمة والشركة ذات المسؤولية المحدودة وشركات الأشخاص، أو بين اختصاصات الإدارة والشركاء والجمعية العامة ومجلس الإدارة.
4) اكتشاف التعميمات القانونية غير الآمنة، والعبارات القطعية التي تحتاج قيدًا، والخلط بين الحق القانوني والممارسة العملية، وبين القاعدة العامة والاستثناء.
5) إذا كان المحتوى قابلًا للتصحيح دون تغيير جوهر الموضوع، أعد صياغته قانونيًا بشكل صحيح قبل النشر.
6) إذا كان الخطأ جوهريًا أو لا يمكن التحقق منه بثقة من المعطيات المتاحة، امنع النشر تمامًا.
7) بعد اجتياز المراجعة القانونية، نفّذ المراجعة اللغوية والتحريرية.
8) أنشئ نسخة LinkedIn أطول بوضوح من Facebook، وليست مجرد اختصار أو إعادة ترتيب؛ تستهدف جمهور الشركات والمهنيين والمحامين والإدارات القانونية وصناع القرار، وتضيف تحليلًا عمليًا وإدارة مخاطر وحوكمة متى كان ذلك مناسبًا، من غير اختراع حقائق قانونية جديدة.
9) راجع جميع التعليقات لغويًا مع الحفاظ على طبيعتها.

قواعد قانونية صارمة:
- البيئة القانونية: جمهورية مصر العربية فقط.
- لا تفترض أن قاعدة تخص نوع شركة تنطبق على نوع آخر.
- إذا ذُكرت عدة أشكال قانونية، افحص كل شكل على حدة. إذا اختلف الحكم، يجب التفريق صراحة أو تضييق نطاق البوست.
- لا تعتبر منصب المدير وحده دليلًا على اختصاصه؛ افحص مصدر الاختصاص وعقد الشركة والنظام القانوني المنطبق.
- لا تستخدم عبارة "القانون واضح" أو "لا يجوز" أو "يحق" أو "يلزم" بصيغة قطعية إلا إذا كانت النتيجة مبررة قانونيًا.
- لا تخترع مصادر. إذا كانت المصادر المدخلة غير كافية للتحقق من نقطة جوهرية، سجّل ذلك.
- لا تعتبر وجود مصدر في النص دليلًا على صحة الاستنتاج؛ افحص مدى انطباقه على النتيجة.
- لا تمرر محتوى فيه خلط جوهري على أنه مجرد مشكلة أسلوب.
- إذا احتاجت النتيجة إلى تحديد قانون أو شكل شركة أو واقعة غير موجودة، اجعل الحالة NEEDS_REVIEW/BLOCK بدل التخمين.
- حافظ على صوت المحتوى ولا تحول Facebook إلى مذكرة قانونية.
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

نفّذ المراجعة على مرحلتين داخل نفس المهمة:

أولًا — LEGAL REVIEW:
- استخرج الادعاءات القانونية الجوهرية في البوست.
- حدّد القانون/النظام القانوني المصري الذي يحكم كل ادعاء متى أمكن.
- افحص مدى انطباق القاعدة على الوقائع والشكل القانوني المذكور.
- افحص أي خلط بين LLC وشركات الأشخاص والشركات المساهمة وغيرها.
- افحص اختصاصات المدير والشركاء والجمعية العامة ومجلس الإدارة وأي جهة أخرى.
- افحص الإجراءات والاشتراطات والآثار القانونية والاستثناءات.
- افحص المصادر المدخلة ومدى دعمها للنتيجة.
- إذا كان هناك خطأ قابل للإصلاح، صحح النص قانونيًا دون اختلاق وقائع.
- إذا كان هناك خطأ جوهري أو عدم يقين يمنع نشر معلومة قانونية موثوقة، اجعل legal_status = BLOCK.

ثانيًا — EDITORIAL/PLATFORM REVIEW:
- Facebook: نسخة واضحة، قوية، مصرية طبيعية، مع أقل تغيير لازم بعد التصحيح القانوني.
- LinkedIn: نسخة أطول بوضوح، تقريبًا 1200–1800 حرفًا عند ملاءمة الموضوع، تتضمن تحليلًا مهنيًا، أثرًا عمليًا، مخاطر، وحوكمة/امتثال متى كان ذلك مناسبًا، دون إضافة حقائق قانونية غير متحققة.
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

مهم جدًا: إذا لم تستطع التحقق بدرجة ثقة مناسبة من قاعدة قانونية جوهرية، لا تخمّن؛ استخدم BLOCK واشرح السبب.
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
