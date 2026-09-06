from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from google import genai


SYSTEM_PROMPT = """
أنت محرر تفاعل اجتماعي لصفحة محامٍ مصري.
أنشئ عددًا متغيرًا وطبيعيًا من تعليقات Facebook بين 5 و20 تعليقًا، واختَر العدد المناسب حسب طبيعة المنشور وقابليته للنقاش. ممنوع الالتزام بعدد ثابت في كل منشور.
أنشئ 5 تعليقات لـLinkedIn.

قاعدة أساسية ومهمة جدًا لـFacebook:
- جميع تعليقات Facebook المطلوب توليدها تُكتب بلسان الصفحة/الحساب نفسه، وليس بلسان متابع أو شخص من الجمهور.
- ممنوع تمامًا انتحال شخصية متابع أو كتابة تعليق يوحي أن الصفحة مجرد فرد من الجمهور.
- الصفحة هي التي تتحدث: تضيف توضيحًا، تصحح تصورًا شائعًا، تشرح نقطة مهمة، تذكر حالة محتملة، أو تضع CTA طبيعيًا عند الحاجة.
- إذا كان من المفيد طرح سؤال، فلا تكتبه كسؤال مجهول من متابع. استخدم فقط مصدرًا حقيقيًا متاحًا للنظام. إذا لم توجد بيانات فعلية عن رسالة أو استفسار، استخدم صياغات صادقة مثل: "من الأسئلة الشائعة اللي بتوصلنا..." أو "من الاستفسارات المتكررة..." أو "سؤال بيتكرر كتير...".
- لا تقل أبدًا "وصلنا سؤال على رسائل الصفحة" أو "جالنا استفسار على الواتساب" إلا إذا كانت هناك بيانات فعلية مؤكدة تثبت ذلك.
- ممنوع اختلاق تجربة شخصية لمتابع أو الادعاء أن شخصًا حقيقيًا قال أو فعل شيئًا لم يثبت وجوده.
- لا تستخدم صيغًا مثل "أنا عندي موقف مشابه" أو "طب لو حصل معايا" أو "أنا عملت كذا" باعتبارها صادرة عن متابع.

تعليقات Facebook يجب أن تكون متنوعة في الوظيفة والأسلوب، وليست إعادة صياغة للمنشور.
وزّعها عند ملاءمة الموضوع بين: توضيح نقطة مهمة، تصحيح تصور شائع، إضافة مثال، تنبيه قانوني بسيط، شرح استثناء أو قيد، سؤال شائع منسوب بصياغة صادقة إلى الأسئلة المتكررة، ودعوة طبيعية لمشاركة المنشور عندما يكون ذلك منطقيًا.
لا تجعل كل التعليقات أسئلة، ولا تجعلها كلها CTA، ولا تجعل دعوات المشاركة أكثرية التعليقات.
CTA الخاص بالصفحة يكون عاديًا وواضحًا، وليس متنكرًا في صورة تعليق متابع. يمكن أن يكون مثل: "لو عندك موقف مشابه ومحتاج تعرف الإطار القانوني، ابعت لنا رسالة بتفاصيله." بحسب طبيعة المنشور.
لا تكرر نفس CTA أو نفس تركيب الجمل في التعليقات.
غيّر طول التعليقات وإيقاعها بشكل طبيعي، واجعل كل تعليق مستقلًا وقابلًا للنشر منفردًا.
ممنوع ادعاء قانوني رقمي غير موجود في المصادر.
ممنوع ذكر أنك ذكاء اصطناعي أو أن هذه التعليقات مولدة آليًا.
ممنوع استخدام عبارات من نوع "رائع جدًا" أو "شكرًا لمتابعتكم" كحشو.

LinkedIn: التعليقات تُكتب بلسان متابع مهني/قارئ للمحتوى، وليست بصوت الصفحة، مع الحفاظ على المهنية وإضافة قيمة.
أعد JSON فقط بهذا الشكل:
{"facebook_comments":["..."],"linkedin_comments":["..."]}
"""

_COMMENT_CACHE: dict[tuple[str, str, str, str], dict[str, list[str]]] = {}
DEFAULT_FALLBACK_MODEL = "gemini-2.5-flash"
MAX_PRIMARY_RETRIES = 3
MAX_FALLBACK_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 5.0
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _extract_status_code(exc: Exception) -> int | None:
    candidates = [
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
        getattr(exc, "status", None),
    ]
    for attr in ("response", "resp"):
        obj = getattr(exc, attr, None)
        if obj is not None:
            candidates.extend([
                getattr(obj, "status_code", None),
                getattr(obj, "status", None),
                getattr(obj, "code", None),
            ])
    for candidate in candidates:
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    match = re.search(r"\b(?:HTTP\s*)?(408|429|500|502|503|504)\b", str(exc))
    return int(match.group(1)) if match else None


def _is_transient(exc: Exception) -> bool:
    return _extract_status_code(exc) in TRANSIENT_STATUS_CODES


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
        raise RuntimeError("Gemini comments response was not valid JSON.")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini comments response contained invalid JSON.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Gemini comments response was not an object.")
    return data


def _normalize(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        key = re.sub(r"\s+", " ", text).casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result[:limit]


def _chat_generate(*, client, model: str, prompt: str) -> Any:
    chat = client.chats.create(model=model)
    return chat.send_message(SYSTEM_PROMPT + "\n" + prompt)


def _generate_with_retry(*, client, model: str, prompt: str, attempts: int, label: str) -> Any:
    for attempt in range(1, attempts + 1):
        try:
            return _chat_generate(client=client, model=model, prompt=prompt)
        except Exception as exc:
            status = _extract_status_code(exc)
            if status not in TRANSIENT_STATUS_CODES or attempt >= attempts:
                raise
            delay = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"Comment AI {label} temporary error ({status}); retry {attempt}/{attempts - 1} in {delay:.0f}s...")
            time.sleep(delay)
    raise RuntimeError("Comment AI generation failed unexpectedly.")


def generate_comments(
    *,
    api_key: str,
    model: str,
    topic: str,
    post: str,
    legal_sources: str = "",
) -> dict[str, list[str]]:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    primary_model = (model or "").strip()
    fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL).strip() or DEFAULT_FALLBACK_MODEL
    cache_key = (primary_model, topic.strip(), post.strip(), legal_sources.strip())
    cached = _COMMENT_CACHE.get(cache_key)
    if cached:
        return {
            "facebook_comments": list(cached["facebook_comments"]),
            "linkedin_comments": list(cached["linkedin_comments"]),
        }

    client = genai.Client(api_key=api_key)
    prompt = f"""
الموضوع: {topic}

المنشور:
{post}

المصادر القانونية المتاحة:
{legal_sources or 'لا توجد مصادر مدخلة.'}

اختر عدد تعليقات Facebook بنفسك بين 5 و20 تعليقًا بناءً على طبيعة الموضوع وحجم النقاش المتوقع. لا تستخدم عددًا ثابتًا بين المنشورات.
لا تقلل العدد لمجرد تقليل المجهود، ولا تزوده لمجرد الوصول إلى 20؛ المطلوب عدد يبدو طبيعيًا لهذا المنشور تحديدًا.

Facebook: اكتب التعليقات بصوت الصفحة نفسها، بالمصري الطبيعي، وبأسلوب بسيط ومهني وغير متكلف.
ممنوع كتابة أي تعليق بلسان متابع أو شخص من الجمهور. الصفحة لا تسأل نفسها بصوت متابع، ولا تنتحل شخصية جمهورها.
اجعل التعليقات تضيف قيمة فعلية: توضيح، تصحيح مفهوم، مثال، قيد أو استثناء، تنبيه عملي، أو سؤال شائع بصياغة صادقة.
إذا احتجت سؤالًا، استخدم فقط مصدرًا حقيقيًا متاحًا للنظام. وبما أنه لا توجد بيانات رسائل واردة ضمن هذه المهمة، لا تدّعِ أن سؤالًا وصل على الرسائل أو الواتساب. استخدم بدلًا من ذلك صيغًا عامة وصادقة مثل: "من الأسئلة الشائعة اللي بتوصلنا..." أو "من الاستفسارات المتكررة..." أو "سؤال بيتكرر كتير...".
لا تستخدم: "طب لو حصل معايا..."، "أنا عندي موقف مشابه..."، "أنا عملت..." أو أي صياغة توهم أن الصفحة متابع حقيقي.

CTA: استخدم CTA عاديًا من الصفحة عندما يكون مناسبًا، مثل الدعوة لإرسال رسالة أو مشاركة المنشور مع شخص قد يحتاج المعلومة. لا تخفِ الـCTA داخل شخصية متابع، ولا تجعل كل التعليقات دعوات لاتخاذ إجراء.
اجعل التعليقات متنوعة بوضوح في الطول والوظيفة والإيقاع، ولا تكرر نفس العبارة أو نفس CTA.
لا تجعل كل التعليقات أسئلة، ولا تجعل كل التعليقات تطلب المشاركة.
كل تعليق يجب أن يكون مستقلًا وقابلًا للنشر منفردًا، وألا يبدو جزءًا من قالب آلي متكرر.

LinkedIn: أنشئ 5 تعليقات مهنية، business-oriented، بلسان قارئ/متابع مهني، وتضيف قيمة.
"""

    try:
        response = _generate_with_retry(client=client, model=primary_model, prompt=prompt, attempts=MAX_PRIMARY_RETRIES, label=f"primary model {primary_model or 'default'}")
    except Exception as primary_exc:
        if not _is_transient(primary_exc) or not fallback_model or fallback_model == primary_model:
            raise
        print(f"Comment AI primary model remained unavailable; switching to fallback model {fallback_model}.")
        response = _generate_with_retry(client=client, model=fallback_model, prompt=prompt, attempts=MAX_FALLBACK_RETRIES, label=f"fallback model {fallback_model}")

    data = _extract_json(getattr(response, "text", ""))
    facebook = _normalize(data.get("facebook_comments"), 20)
    linkedin = _normalize(data.get("linkedin_comments"), 5)
    if len(facebook) < 5 or len(linkedin) < 5:
        raise RuntimeError("Comment engine returned fewer than 5 Facebook or 5 LinkedIn comments.")

    result = {"facebook_comments": facebook, "linkedin_comments": linkedin}
    _COMMENT_CACHE[cache_key] = result
    print(f"Adaptive comment count selected: Facebook={len(facebook)}/20 | LinkedIn={len(linkedin)}/5")
    return {
        "facebook_comments": list(facebook),
        "linkedin_comments": list(linkedin),
    }
