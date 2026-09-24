from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any

from google import genai

from engagement_strategy import normalize_comment, comment_schedule_offsets as shared_schedule_offsets

DEFAULT_FALLBACK_MODEL = "gemini-2.5-flash"
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}
PRIMARY_RETRIES = 3
FALLBACK_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 5.0
LINKEDIN_MIN_COMMENTS = 5
LINKEDIN_MAX_COMMENTS = 8

SYSTEM_PROMPT = """
أنت محرر تفاعل مهني لصفحة محامٍ مصري على LinkedIn.
أنشئ تعليقات يكتبها صاحب الحساب على منشوراته هو لإضافة قيمة حقيقية للنقاش.
ممنوع الحشو، والمجاملة العامة، وإعادة صياغة المنشور، واختلاق وقائع أو مصادر أو تجارب.
كل تعليق يجب أن يرتبط مباشرة بالمنشور ويضيف زاوية مختلفة.
لا تجعل كل التعليقات أسئلة أو CTA. لا تنهِ أي تعليق بنقطة ولا تستخدم صياغة مصقولة بشكل مفرط أو نمطًا متكررًا
في كل حزمة، اجعل CTA قويًا ومباشرًا في تعليق واحد فقط عندما يكون مناسبًا للموضوع، ويكون مرتبطًا بهدف المنشور وموجهًا للفئة المستهدفة (مثل صاحب عمل، HR، مدير، مستثمر أو شخص يواجه مشكلة قانونية)، وليس CTA عامًا من نوع "ما رأيكم؟".
التعليقات الأخرى يجب أن تضيف قيمة تحليلية مستقلة بدون دعوة لاتخاذ إجراء.
اللغة عربية مصرية مهنية وواضحة وتناسب LinkedIn.
أعد JSON فقط.
""".strip()

def _extract_status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass
    match = re.search(r"\b(?:HTTP\s*)?(408|429|500|502|503|504)\b", str(exc))
    return int(match.group(1)) if match else None

def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("LinkedIn comment engine returned invalid JSON.")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("LinkedIn comment engine returned a non-object JSON response.")
    return value

def _normalize_comments(value: Any, count: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        text = normalize_comment(str(item or ""))
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result[:count]

def choose_comment_count(post_urn: str) -> int:
    """Deterministically select 5-8 comments for LinkedIn, independently of the shared 5-10 strategy."""
    key = str(post_urn or "").strip().encode("utf-8")
    if not key:
        return LINKEDIN_MIN_COMMENTS
    digest = hashlib.sha256(key).digest()
    return LINKEDIN_MIN_COMMENTS + (digest[0] % (LINKEDIN_MAX_COMMENTS - LINKEDIN_MIN_COMMENTS + 1))

def comment_schedule_offsets(count: int) -> list[int]:
    """Return LinkedIn schedule offsets for at most 8 comments, 15 minutes apart."""
    count = max(LINKEDIN_MIN_COMMENTS, min(LINKEDIN_MAX_COMMENTS, int(count)))
    return shared_schedule_offsets(count)


def _generate(*, client, model: str, prompt: str, attempts: int) -> Any:
    for attempt in range(1, attempts + 1):
        try:
            return client.models.generate_content(model=model, contents=SYSTEM_PROMPT + "\n\n" + prompt)
        except Exception as exc:
            status = _extract_status_code(exc)
            if status not in TRANSIENT_STATUS_CODES or attempt >= attempts:
                raise
            delay = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"LinkedIn comment AI temporary error ({status}); retry {attempt}/{attempts - 1} in {delay:.0f}s...")
            time.sleep(delay)
    raise RuntimeError("LinkedIn comment generation failed.")

def generate_linkedin_comments(*, api_key: str, model: str, post_urn: str, topic: str, post: str, legal_sources: str = "", count: int | None = None) -> list[str]:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    count = count if count is not None else choose_comment_count(post_urn)
    if count < LINKEDIN_MIN_COMMENTS or count > LINKEDIN_MAX_COMMENTS:
        raise ValueError("LinkedIn comment count must be between 5 and 8.")
    fallback = os.getenv("GEMINI_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL).strip() or DEFAULT_FALLBACK_MODEL
    prompt = f"""
أنشئ بالضبط {count} تعليقات مختلفة لهذا المنشور، مع اختلاف واضح في الطول والإيقاع والزاوية
الموضوع: {topic}
نص المنشور:
{post}
المصادر القانونية المتاحة:
{legal_sources or "لا توجد مصادر قانونية مدخلة."}

استخدم أدوارًا مختلفة بحسب ملاءمة المنشور: توضيح دقيق، مثال عملي، قيد أو استثناء، أثر إداري أو تجاري، تصحيح تصور شائع، سؤال مهني، أو خلاصة عملية.
اجعل تعليقًا واحدًا فقط، عند ملاءمة الموضوع، يحمل CTA قويًا مرتبطًا مباشرة باتجاه المنشور؛ لا تكرر الـCTA في بقية التعليقات.
لا تستخدم نفس الزاوية أو الصياغة مرتين. لا تعيد صياغة نص المنشور ولا تستخدم مجاملات فارغة.
أعد JSON بالشكل: {{"linkedin_comments":["...", "..."]}}
""".strip()
    client = genai.Client(api_key=api_key)
    try:
        response = _generate(client=client, model=model.strip(), prompt=prompt, attempts=PRIMARY_RETRIES)
    except Exception as primary_exc:
        status = _extract_status_code(primary_exc)
        if status not in TRANSIENT_STATUS_CODES or not fallback or fallback == model.strip():
            raise
        response = _generate(client=client, model=fallback, prompt=prompt, attempts=FALLBACK_RETRIES)
    data = _extract_json(getattr(response, "text", ""))
    comments = _normalize_comments(data.get("linkedin_comments"), count)
    if len(comments) != count:
        raise RuntimeError(f"LinkedIn comment engine returned {len(comments)} unique comments; expected {count}.")
    return comments
