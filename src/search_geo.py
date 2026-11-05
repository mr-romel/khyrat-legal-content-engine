from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

SEARCH_GEO_HEADERS = [
    "Post ID",
    "Topic",
    "Platform",
    "Search Intent",
    "Primary Search Question",
    "Related Questions",
    "Jurisdiction",
    "Legal Entity",
    "Answer Extract",
    "Supporting Evidence",
    "Local Intent",
    "Page Type",
    "SEO Title",
    "Meta Description",
    "Slug",
    "GEO Summary",
    "Author/Provenance",
    "Updated At",
]

JURISDICTION = "مصر"

LEGAL_PATTERNS = [
    (r"فصل|مرتب|عامل|موظف|إجاز|جزاء|استقالة", "قانون العمل"),
    (r"عقد|اتفاق|بند|شرط|تعاقد", "العقود"),
    (r"شركة|شريك|مدير|تأسيس|حصة|جمعية", "قانون الشركات"),
    (r"إيصال|شيك|دين|مديون|مطالبة|تعويض", "مدني وتجاري"),
    (r"طلاق|نفقة|حضانة|زواج|أسرة", "الأحوال الشخصية"),
    (r"جنائي|حبس|بلاغ|محضر|جريمة|اتهام", "القانون الجنائي"),
]

INTENT_RULES = [
    (("ازاي", "إزاي", "كيف", "ماذا أفعل", "أعمل إيه", "اعمل ايه"), "HOW_TO"),
    (("هل يجوز", "هل ينفع", "يجوز", "هل يحق", "هل يصح"), "QUESTION"),
    (("حقوق", "حق", "واجب", "يستحق"), "INFORMATIONAL"),
    (("مشكلة", "نزاع", "اتظلم", "فصل", "رفض", "امتنع"), "PROBLEM_SOLVING"),
]

def _now() -> str:
    return datetime.now().astimezone().isoformat()

def _clean(value: Any, limit: int = 500) -> str:
    text = str(value or "")
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]

def _slug(text: str) -> str:
    # Arabic Unicode block includes punctuation marks (including ؟), so strip
    # punctuation explicitly before applying the Arabic-letter allowlist.
    normalized = re.sub(r"[؟،؛：:!,.…()\[\]{}<>«»“”‘’\"'ـ]+", " ", str(text or "").casefold())
    value = re.sub(r"[^\w\u0621-\u064a\u0660-\u0669\s-]", "", normalized)
    value = re.sub(r"[-\s]+", "-", value).strip("-")
    return value[:90] or "legal-question"
def infer_legal_entity(topic: str, post: str = "") -> str:
    text = f"{topic} {post}"
    for pattern, entity in LEGAL_PATTERNS:
        if re.search(pattern, text):
            return entity
    return "استشارة قانونية عامة"

def infer_intent(topic: str, post: str = "") -> str:
    text = f"{topic} {post}"
    for phrases, intent in INTENT_RULES:
        if any(p in text for p in phrases):
            return intent
    return "INFORMATIONAL"

def build_primary_question(topic: str, post: str = "") -> str:
    topic = _clean(topic, 160)
    post = _clean(post, 220)
    if "؟" in post:
        first = post.split("؟", 1)[0].strip()
        if first:
            return first + "؟"
    if any(x in topic for x in ("هل", "ازاي", "إزاي", "كيف", "ماذا")):
        return topic.rstrip("؟") + "؟"
    return f"ما الحكم القانوني في {topic} في مصر؟"

def build_related_questions(topic: str, post: str = "") -> str:
    entity = infer_legal_entity(topic, post)
    q = build_primary_question(topic, post).rstrip("؟")
    variants = [
        q + "؟",
        f"ما الشروط أو الحالات المرتبطة بذلك في {JURISDICTION}؟",
        f"ما الخطوة العملية التالية في هذه الحالة؟",
        f"ما الاستثناءات أو المواعيد التي يجب الانتباه لها؟",
    ]
    if entity != "استشارة قانونية عامة":
        variants[1] = f"ما القاعدة الأساسية في {entity} بالنسبة لهذا الموضوع؟"
    return " | ".join(dict.fromkeys(variants))

def build_answer_extract(topic: str, post: str = "") -> str:
    text = _clean(post, 300)
    if text:
        first_sentence = re.split(r"[.!؟]", text)[0].strip()
        if first_sentence:
            return _clean(first_sentence, 280)
    return f"الإجابة تعتمد على تفاصيل الواقعة والنص القانوني المنطبق في {JURISDICTION}، ولا يصح حسم النتيجة من عنوان الموضوع وحده."

def build_evidence(topic: str, post: str = "") -> str:
    return "لم تُرفق مصادر قانونية محددة في سجل المحتوى؛ يلزم التحقق من النص الرسمي أو الجهة المختصة قبل الاعتماد."

def build_local_intent(topic: str, post: str = "") -> str:
    """Represent the firm's real delivery model without implying nationwide court attendance."""
    text = f"{topic} {post}"
    online_markers = ("أونلاين", "اونلاين", "عن بعد", "عن بُعد", "استشارة", "استشارات", "استفسار")
    case_markers = ("قضية", "دعوى", "محكمة", "ترافع", "حضور", "تنفيذ", "جنائي", "مدني", "أسرة", "عمالي")
    if any(marker in text for marker in online_markers) and not any(marker in text for marker in case_markers):
        return "ONLINE_CONSULTATIONS | ALL_EGYPT"
    if any(marker in text for marker in case_markers):
        return "CASEWORK_AND_COURT_ATTENDANCE | CAIRO_AND_GIZA"
    return "CAIRO_AND_GIZA_CASEWORK | ALL_EGYPT_ONLINE_CONSULTATIONS"

def build_page_type(intent: str, entity: str) -> str:
    if intent == "HOW_TO":
        return "HOW_TO"
    if intent == "QUESTION":
        return "FAQ"
    if "شركة" in entity:
        return "LEGAL_GUIDE"
    return "LEGAL_EXPLAINER"

def build_metadata(*, post_id: str, topic: str, post: str, platform: str, legal_sources: str = "") -> dict[str, str]:
    topic = _clean(topic, 180)
    post = _clean(post, 700)
    intent = infer_intent(topic, post)
    entity = infer_legal_entity(topic, post)
    question = build_primary_question(topic, post)
    extract = build_answer_extract(topic, post)
    title = _clean(question, 65)
    description = _clean(f"{extract} شرح عملي مبني على القواعد القانونية المصرية والمصادر ذات الصلة.", 155)
    return {
        "Post ID": _clean(post_id, 120),
        "Topic": topic,
        "Platform": _clean(platform, 40).upper(),
        "Search Intent": intent,
        "Primary Search Question": question,
        "Related Questions": build_related_questions(topic, post),
        "Jurisdiction": JURISDICTION,
        "Legal Entity": entity,
        "Answer Extract": extract,
        "Supporting Evidence": _clean(legal_sources, 700) or build_evidence(topic, post),
        "Local Intent": build_local_intent(topic, post),
        "Page Type": build_page_type(intent, entity),
        "SEO Title": title,
        "Meta Description": description,
        "Slug": _slug(question),
        "GEO Summary": _clean(
            f"سؤال: {question} | جواب مختصر: {extract} | الاختصاص: {JURISDICTION} | المجال: {entity} | "
            "نطاق الخدمة: متابعة القضايا والحضور والترافع في القاهرة والجيزة؛ الاستشارات القانونية أونلاين لجميع محافظات مصر.",
            700,
        ),
        "Author/Provenance": "اسأل محمود | مسودة مولدة آليًا وتستلزم مراجعة قانونية بشرية قبل الاعتماد",
        "Updated At": _now(),
    }

def build_live_page_metadata(*, title: str, description: str, answer: str, topic: str, keywords: list[str] | None = None) -> dict[str, str | list[str]]:
    """Normalize metadata from the actual reviewed article; never invent legal claims or sources."""
    clean_title = _clean(title, 110)
    clean_answer = _clean(answer, 1200)
    clean_description = _clean(description, 180) or _clean(clean_answer, 155)
    clean_keywords = list(dict.fromkeys(_clean(item, 60) for item in (keywords or []) if _clean(item, 60)))[:12]
    if not clean_title or not clean_answer:
        raise ValueError("Live page metadata requires a real article title and answer-first lead.")
    return {
        "title": clean_title,
        "description": clean_description,
        "answer": clean_answer,
        "topic": _clean(topic, 180),
        "keywords": clean_keywords,
        "jurisdiction": JURISDICTION,
    }


def record_search_geo(service, spreadsheet_id: str, *, post_id: str, topic: str, post: str, platform: str, legal_sources: str = "") -> None:
    from content_system import _append, _ensure_sheet
    from sheets import get_values
    _ensure_sheet(service, spreadsheet_id, "SearchGEO", SEARCH_GEO_HEADERS)
    existing = get_values(service, spreadsheet_id, "SearchGEO!A:A")
    if any(str(row[0]).strip() == str(post_id).strip() for row in existing[1:] if row):
        return
    data = build_metadata(
        post_id=post_id,
        topic=topic,
        post=post,
        platform=platform,
        legal_sources=legal_sources,
    )
    _append(service, spreadsheet_id, "SearchGEO", [data[h] for h in SEARCH_GEO_HEADERS])

def build_search_geo_index(rows: list[dict[str, str]]) -> dict[str, object]:
    return {
        "generated_at": _now(),
        "jurisdiction": JURISDICTION,
        "pages": [
            {
                "post_id": row.get("Post ID", ""),
                "question": row.get("Primary Search Question", ""),
                "intent": row.get("Search Intent", ""),
                "entity": row.get("Legal Entity", ""),
                "slug": row.get("Slug", ""),
                "summary": row.get("GEO Summary", ""),
            }
            for row in rows
            if row.get("Post ID")
        ],
    }
