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
    research_config = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.1)
    response = _generate(client=client, model=model or DEFAULT_FALLBACK_MODEL, prompt=prompt, attempts=MAX_RESEARCH_RETRIES, label="deep web legal research", config=research_config)
    text = str(getattr(response, "text", "") or "").strip()
    sources = extract_grounding_sources(response)
    if len(text) < 300:
        raise RuntimeError("Deep legal web research returned insufficient evidence.")
    if not sources:
        raise RuntimeError("Deep legal web research returned no verifiable grounding sources.")
    return text, sources


def build_review_context(*, client, model: str, topic: str, facebook_post: str, legal_sources: str) -> tuple[bool, str, list[dict[str, str]]]:
    try:
        research, sources = _research_web(client=client, model=model, topic=topic, facebook_post=facebook_post, legal_sources=legal_sources)
        print(f"Legal research gate: completed with {len(sources)} grounded sources.")
        return True, research, sources
    except Exception as exc:
        print(f"Legal research gate unavailable: {exc}")
        print("Legal research gate: switching to SIMPLE REVIEW mode; publication will continue unless the post itself contains an obvious unsafe legal assertion.")
        return False, "", []
