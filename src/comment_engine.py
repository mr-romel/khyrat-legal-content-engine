from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from google import genai


SYSTEM_PROMPT = """
أنت محرر تفاعل اجتماعي لصفحة محامٍ مصري.
أنشئ 5 تعليقات مختلفة تمامًا على نفس المنشور.
التعليقات ليست تكرارًا للمنشور وليست حشوًا.
كل تعليق يجب أن يضيف قيمة حقيقية، مثل سؤال ذكي، توضيح عملي، تصحيح تصور شائع، سيناريو قصير، أو دعوة طبيعية للنقاش.
ممنوع ادعاء قانوني رقمي غير موجود في المصادر.
ممنوع ذكر أنك ذكاء اصطناعي.
ممنوع استخدام عبارات من نوع "رائع جدًا" أو "شكرًا لمتابعتكم" كحشو.
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


def _normalize(value: Any) -> list[str]:
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
    return result[:5]


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
            print(
                f"Comment AI {label} temporary error ({status}); "
                f"retry {attempt}/{attempts - 1} in {delay:.0f}s..."
            )
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
        print("Comment engine: reusing generated comment package for the second platform.")
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

أنشئ 5 تعليقات Facebook و5 تعليقات LinkedIn.
Facebook: مصري طبيعي، تفاعلي، بسيط.
LinkedIn: مهني، business-oriented، ويضيف قيمة.
اجعل كل تعليق مختلفًا في الوظيفة والأسلوب.
"""

    try:
        response = _generate_with_retry(
            client=client,
            model=primary_model,
            prompt=prompt,
            attempts=MAX_PRIMARY_RETRIES,
            label=f"primary model {primary_model or 'default'}",
        )
    except Exception as primary_exc:
        if not _is_transient(primary_exc) or not fallback_model or fallback_model == primary_model:
            raise
        print(f"Comment AI primary model remained unavailable; switching to fallback model {fallback_model}.")
        response = _generate_with_retry(
            client=client,
            model=fallback_model,
            prompt=prompt,
            attempts=MAX_FALLBACK_RETRIES,
            label=f"fallback model {fallback_model}",
        )

    data = _extract_json(getattr(response, "text", ""))
    facebook = _normalize(data.get("facebook_comments"))
    linkedin = _normalize(data.get("linkedin_comments"))
    if len(facebook) < 5 or len(linkedin) < 5:
        raise RuntimeError("Comment engine returned fewer than 5 comments per platform.")

    result = {"facebook_comments": facebook, "linkedin_comments": linkedin}
    _COMMENT_CACHE[cache_key] = result
    return {
        "facebook_comments": list(facebook),
        "linkedin_comments": list(linkedin),
    }
