from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any

from google import genai

from engagement_strategy import normalize_comment, comment_schedule_offsets as shared_schedule_offsets, choose_comment_count as shared_choose_comment_count

DEFAULT_FALLBACK_MODEL = "gemini-2.5-flash"
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}
# Once the Gemini quota is exhausted, fail fast for the remainder of the run
# and use deterministic comments instead of burning time on retries.
_GEMINI_QUOTA_EXHAUSTED = False
PRIMARY_RETRIES = 3
FALLBACK_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 5.0
LINKEDIN_MIN_COMMENTS = 3
LINKEDIN_MAX_COMMENTS = 7

SYSTEM_PROMPT = """
أنت محرر تفاعل مهني لصفحة محامٍ مصري على LinkedIn.
أنشئ تعليقات يكتبها صاحب الحساب على منشوراته هو لإضافة قيمة حقيقية للنقاش.
ممنوع الحشو، والمجاملة العامة، وإعادة صياغة المنشور، واختلاق وقائع أو مصادر أو تجارب.
كل تعليق يجب أن يرتبط مباشرة بالمنشور ويضيف زاوية مختلفة.
لا تجعل كل التعليقات أسئلة أو CTA. لا تنهِ أي تعليق بنقطة ولا تستخدم صياغة مصقولة بشكل مفرط أو نمطًا متكررًا. ممنوع البدء بعنوان المنشور ثم شرطة أو نقطتين وإضافة "زاوية جديدة" أو "Checklist" أو عنوان فرعي تحليلي؛ التعليق ليس عنوانًا بديلًا للمنشور
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

AI_STYLE_PATTERNS = (
    "النقطة الأهم هنا",
    "من زاوية أخرى",
    "من المهم الإشارة إلى",
    "هذا يسلط الضوء على",
    "لا شك أن",
    "وهنا تكمن أهمية",
    "زاوية جديدة",
    "checklist",
    "قائمة مراجعة",
)

STRUCTURAL_AI_PATTERNS = (
    r"\s*[—–-]\s*(?:زاوية|نقطة|رؤية|مقاربة|قراءة|مدخل)",
    r"\b(?:زاوية جديدة|checklist|قائمة مراجعة)\s*[:：]",
)

def _humanish_linkedin(text: str, post: str) -> bool:
    value = normalize_comment(text or "")
    if not value:
        return False
    folded = re.sub(r"\s+", " ", value).strip().casefold()
    if any(p.casefold() in folded for p in AI_STYLE_PATTERNS):
        return False
    if any(re.search(p, folded, flags=re.I) for p in STRUCTURAL_AI_PATTERNS):
        return False
    if len(value) > 420:
        return False
    post_head = re.sub(r"\s+", " ", (post or "").split("\n", 1)[0]).strip().casefold()
    head_words = re.findall(r"[\wء-ي]{3,}", post_head)
    comment_words = re.findall(r"[\wء-ي]{3,}", folded)
    if len(head_words) >= 6 and len(comment_words) >= 6:
        shared_prefix = 0
        for a, b in zip(head_words[:10], comment_words[:10]):
            if a != b:
                break
            shared_prefix += 1
        if shared_prefix >= 6:
            return False
    return True

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

def choose_comment_count(topic_or_key: str, post: str = "") -> int:
    """Use the same deterministic 3-7 target as Facebook for the same post."""
    # Comment count is derived from the published post only; Sheet topic/title is never used.
    key = str(post or "").strip()
    if not key:
        return LINKEDIN_MIN_COMMENTS
    return shared_choose_comment_count(key)

def comment_schedule_offsets(count: int) -> list[int]:
    """Return LinkedIn schedule offsets for at most 7 comments, 15 minutes apart."""
    count = max(LINKEDIN_MIN_COMMENTS, min(LINKEDIN_MAX_COMMENTS, int(count)))
    return shared_schedule_offsets(count)


def _generate(*, client, model: str, prompt: str, attempts: int) -> Any:
    global _GEMINI_QUOTA_EXHAUSTED
    if _GEMINI_QUOTA_EXHAUSTED:
        raise RuntimeError("Gemini quota already exhausted in this worker run.")
    for attempt in range(1, attempts + 1):
        try:
            return client.models.generate_content(model=model, contents=SYSTEM_PROMPT + "\n\n" + prompt)
        except Exception as exc:
            status = _extract_status_code(exc)
            if status == 429:
                _GEMINI_QUOTA_EXHAUSTED = True
                raise
            if status not in TRANSIENT_STATUS_CODES or attempt >= attempts:
                raise
            delay = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"LinkedIn comment AI temporary error ({status}); retry {attempt}/{attempts - 1} in {delay:.0f}s...")
            time.sleep(delay)
    raise RuntimeError("LinkedIn comment generation failed.")

def _fallback_linkedin_comments(post: str, count: int) -> list[str]:
    """Deterministic comments must derive from the published post, never the Sheet title."""
    post_text = re.sub(r"\s+", " ", str(post or "")).strip()
    templates = [
        "الوقائع والمستندات هي اللي بتحسم التطبيق العملي، مش القاعدة العامة وحدها",
        "من منظور إداري، تحديد المسؤوليات والمواعيد والالتزامات قبل التنفيذ يقلل تكلفة التصحيح",
        "التفصيل الصغير في المستند أو الإجراء ممكن يغيّر التقييم القانوني للموقف بالكامل",
        "القرار السريع مش دايمًا الأقل تكلفة، خصوصًا لما يكون له أثر تعاقدي أو مالي",
        "المهم إن القرار يتبني على الوقائع الفعلية والمستندات الموجودة، مش على وصف مختصر للمشكلة",
        "المراجعة القانونية هنا أداة لإدارة المخاطر قبل ما المشكلة تتحول إلى نزاع أو تكلفة إضافية",
        "لما يكون قدام الإدارة أكتر من بديل، مقارنة الأثر القانوني والتجاري لكل بديل بتخلي القرار أوضح",
    ]
    # The published post is the only source of subject matter. The fallback
    # never interpolates the spreadsheet topic/title.
    if not post_text:
        return [normalize_comment(x) for x in templates[:count]]
    return [normalize_comment(x) for x in templates[:count]]


def generate_linkedin_comments(*, api_key: str, model: str, post_urn: str, topic: str, post: str, legal_sources: str = "", count: int | None = None) -> list[str]:
    count = count if count is not None else choose_comment_count(topic, post)
    if not api_key:
        print("GEMINI_API_KEY is missing; using deterministic LinkedIn comments.")
        return _fallback_linkedin_comments(post, count)
    # 3-7 is the target bundle size; incremental refill may legitimately request 1-2 remaining comments
    if count < 1 or count > LINKEDIN_MAX_COMMENTS:
        raise ValueError("LinkedIn comment count must be between 1 and 7.")
    fallback = os.getenv("GEMINI_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL).strip() or DEFAULT_FALLBACK_MODEL
    prompt = f"""
أنشئ بالضبط {count} تعليقات مختلفة لهذا المنشور، مع اختلاف واضح في الطول والإيقاع والزاوية.
المصدر الوحيد لفهم موضوع التعليق هو نص المنشور المنشور فعليًا أدناه.
ممنوع استخدام عنوان أو موضوع من Google Sheets، وممنوع استدعاء أو إعادة إنتاج عنوان/موضوع غير موجود داخل نص المنشور.
نص المنشور المنشور فعليًا:
{post}
المصادر القانونية المتاحة:
{legal_sources or "لا توجد مصادر قانونية مدخلة."}

استخدم أدوارًا مختلفة بحسب ملاءمة المنشور: توضيح دقيق، مثال عملي، قيد أو استثناء، أثر إداري أو تجاري، تصحيح تصور شائع، سؤال مهني، أو خلاصة عملية.
اجعل تعليقًا واحدًا فقط، عند ملاءمة الموضوع، يحمل CTA قويًا مرتبطًا مباشرة باتجاه المنشور؛ لا تكرر الـCTA في بقية التعليقات.
لا تستخدم نفس الزاوية أو الصياغة مرتين. لا تعيد صياغة نص المنشور ولا تستخدم مجاملات فارغة.
أعد JSON بالشكل: {{"linkedin_comments":["...", "..."]}}
""".strip()
    if _GEMINI_QUOTA_EXHAUSTED:
        print("Gemini quota already exhausted in this worker run; using deterministic LinkedIn comments without another API call.")
        return _fallback_linkedin_comments(post, count)
    client = genai.Client(api_key=api_key)
    try:
        response = _generate(client=client, model=model.strip(), prompt=prompt, attempts=PRIMARY_RETRIES)
    except Exception as primary_exc:
        status = _extract_status_code(primary_exc)
        if status == 429:
            print("LinkedIn comment AI quota exhausted (429); using deterministic comments immediately.")
            return _fallback_linkedin_comments(post, count)
        if status in TRANSIENT_STATUS_CODES and fallback and fallback != model.strip():
            try:
                response = _generate(client=client, model=fallback, prompt=prompt, attempts=FALLBACK_RETRIES)
            except Exception as fallback_exc:
                print(f"LinkedIn comment AI unavailable; using deterministic fallback: {fallback_exc}")
                return _fallback_linkedin_comments(post, count)
        else:
            print(f"LinkedIn comment AI unavailable; using deterministic fallback: {primary_exc}")
            return _fallback_linkedin_comments(post, count)
    try:
        data = _extract_json(getattr(response, "text", ""))
        comments = _normalize_comments(data.get("linkedin_comments"), count)
        comments = [c for c in comments if _humanish_linkedin(c, post)]
        if len(comments) != count:
            raise RuntimeError(
                f"LinkedIn comment engine returned {len(comments)} unique comments; expected {count}."
            )
    except Exception as exc:
        print(f"LinkedIn comment AI output validation failed; using deterministic fallback: {exc}")
        return _fallback_linkedin_comments(post, count)
    return comments
