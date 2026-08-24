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
أنت المراجع التحريري النهائي لمحتوى قانوني مصري قبل نشره على وسائل التواصل.

وظيفتك أربع مهام مترابطة:
1) مراجعة البوست العربي وتصحيح الأخطاء الإملائية والنحوية وعلامات الترقيم.
2) الحفاظ على المعنى القانوني كما هو، وعدم اختراع مادة أو حكم أو رقم أو عقوبة أو تاريخ.
3) إنشاء نسخة LinkedIn من نفس الموضوع، مختلفة في الصياغة عن Facebook وأكثر مهنية وBusiness-oriented، مع مراعاة أن الجمهور يشمل المحامين والشركات والموظفين والإدارات القانونية وصناع القرار.
4) مراجعة وتصحيح جميع التعليقات لغويًا قبل النشر، مع الحفاظ على طبيعتها وعدم تحويلها إلى لغة رسمية متكلفة.

قواعد إلزامية:
- لا تضف أي معلومة قانونية غير موجودة في النص أو المصادر القانونية.
- لا تغيّر النتيجة أو الحكم القانوني لمجرد تحسين الأسلوب.
- لا تحذف تحفظًا قانونيًا مهمًا.
- لا تجعل LinkedIn نسخة من Facebook مع استبدال بعض الكلمات؛ أعد بناء الصياغة بزاوية مهنية مختلفة.
- LinkedIn يجب أن يركز عند الملاءمة على الأثر العملي، إدارة المخاطر، الامتثال، العقود، سياسات العمل، الحوكمة، أو القرار المهني، بحسب طبيعة الموضوع.
- لا تستخدم لغة تسويقية مبتذلة أو مبالغات.
- حافظ على العربية السليمة والواضحة.
- في Facebook يمكن الاحتفاظ بلمسة مصرية طبيعية.
- في LinkedIn استخدم عربية مهنية واضحة، ويمكن استخدام مصطلح إنجليزي تجاري عند الحاجة فقط.
- صحح الهمزات والتاء المربوطة والهاء والياء والألف المقصورة وعلامات الترقيم والمسافات.
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
                f"Editorial review {label} temporary error ({status}); "
                f"retry {attempt}/{attempts - 1} in {delay:.0f}s..."
            )
            time.sleep(delay)
    raise RuntimeError("Editorial review failed unexpectedly.")


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
        raise RuntimeError("Editorial review response was not valid JSON.")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Editorial review response contained invalid JSON.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Editorial review response was not an object.")
    return data


def _clean_list(value: Any, minimum: int = 5) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeError("Editorial review returned an invalid comment list.")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        key = re.sub(r"\s+", " ", text).casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    if len(result) < minimum:
        raise RuntimeError(f"Editorial review returned fewer than {minimum} comments.")
    return result[:5]


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

المصادر القانونية المتاحة:
{legal_sources or "لا توجد مصادر قانونية مدخلة."}

Facebook قبل المراجعة:
{facebook_post}

تعليقات Facebook قبل المراجعة:
{json.dumps(facebook_comments, ensure_ascii=False)}

تعليقات LinkedIn قبل المراجعة:
{json.dumps(linkedin_comments, ensure_ascii=False)}

المطلوب:
- صحح Facebook مع أقل تغيير ممكن يحافظ على المعنى والصوت.
- أنشئ LinkedIn من نفس الموضوع ومن نفس الحقائق، لكن بصياغة مهنية مختلفة بوضوح وأكثر ملاءمة لجمهور الشركات والمهنيين.
- صحح تعليقات Facebook.
- صحح تعليقات LinkedIn.

أعد JSON بهذا الشكل فقط:
{{
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
            label=f"primary model {primary_model or 'default'}",
        )
    except Exception as primary_exc:
        status = _extract_status_code(primary_exc)
        if status not in TRANSIENT_STATUS_CODES or not fallback_model or fallback_model == primary_model:
            raise
        print(f"Editorial review primary model unavailable; switching to {fallback_model}.")
        response = _generate(
            client=client,
            model=fallback_model,
            prompt=prompt,
            attempts=MAX_FALLBACK_RETRIES,
            label=f"fallback model {fallback_model}",
        )

    data = _extract_json(getattr(response, "text", ""))
    facebook_post = str(data.get("facebook_post", "")).strip()
    linkedin_post = str(data.get("linkedin_post", "")).strip()
    if not facebook_post or not linkedin_post:
        raise RuntimeError("Editorial review returned an empty post.")

    facebook = _clean_list(data.get("facebook_comments"))
    linkedin = _clean_list(data.get("linkedin_comments"))

    return {
        "facebook_post": facebook_post,
        "linkedin_post": linkedin_post,
        "facebook_comments": facebook,
        "linkedin_comments": linkedin,
    }
