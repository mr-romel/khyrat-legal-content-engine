from __future__ import annotations

import json
from typing import Any

from google import genai

from editorial_research import (
    DEFAULT_FALLBACK_MODEL,
    MAX_FALLBACK_RETRIES,
    MAX_PRIMARY_RETRIES,
    SYSTEM_PROMPT,
    _clean_list,
    _extract_json,
    _extract_status_code,
    _generate,
    _normalize_status,
    _research_web,
)
from legal_reference_registry import build_reference_context, format_grounding_sources


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
        research, grounded_sources = _research_web(client=client, model=primary_model, topic=topic, facebook_post=facebook_post, legal_sources=legal_sources)
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
        if research_available else
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
        response = _generate(client=client, model=primary_model, prompt=prompt, attempts=MAX_PRIMARY_RETRIES, label=f"primary model {primary_model}")
    except Exception as primary_exc:
        status = _extract_status_code(primary_exc)
        if status not in {408, 429, 500, 502, 503, 504} or fallback_model == primary_model:
            raise
        print(f"Legal/editorial review primary model unavailable; switching to {fallback_model}.")
        response = _generate(client=client, model=fallback_model, prompt=prompt, attempts=MAX_FALLBACK_RETRIES, label=f"fallback model {fallback_model}")

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
            raise RuntimeError("Publication blocked by comprehensive legal/readability gate: " + (reason or "insufficient legal certainty or unacceptable content quality."))
    else:
        if readability_status == "BLOCK" or legal_status == "BLOCK":
            raise RuntimeError("Publication blocked by simple legal/readability review: " + (reason or "the post could not be made safe by simple rewriting."))
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
