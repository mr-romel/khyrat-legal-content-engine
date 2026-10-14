from __future__ import annotations

import json
from typing import Any
from ai_router import create_client, has_any_provider_key

DEFAULT_MODEL = "gemini-3.6-flash"
SYSTEM_PROMPT = """You are the senior Egyptian legal editor for Ask Mahmoud. Turn a reviewed social post into an original, human-sounding Arabic web article. Write in professional Egyptian Arabic with natural variation, as if written by an Egyptian lawyer with real practice experience. The reader comes first. Improve search discoverability and answer-engine comprehension without keyword stuffing. Use Egypt and Egyptian law only when supported by the supplied material. Never invent a statute number, penalty, ruling, deadline, procedure, exception, fact, or source. Prefer the newest effective Egyptian legislation and explicitly reconcile recent amendments before explaining the rule. When the supplied LEGAL RESEARCH PACKET contains a verified, directly relevant Court of Cassation or Supreme Administrative Court judgment/principle, use it to strengthen the article. Any quotation must be copied only from the supplied verified source, stay under 24 words per source, and be followed by the court and exact appeal/cassation number; include the hearing date when supplied. Never invent or infer a case number, date, quotation, statute number, or current legal rule. If no verified judgment is available, use a verified general principle or current legislation instead. Never rely on an older judicial interpretation as the current rule when a later amendment changed the relevant statutory text. Treat the supplied topic as internal subject metadata only, not as copy to reproduce. Do not mention or reproduce spreadsheet/editorial metadata such as زاوية المحتوى, الزاوية, زاوية جديدة, الهدف, الـهدف, pillar, objective, hook, CTA, نوع المحتوى, أو أي تعليمات تخطيطية. Never copy the spreadsheet topic/title verbatim into the article title or body. Build the article from the underlying legal facts and reader questions instead.

SEO REQUIREMENTS: Match one clear primary search intent. Use a precise, natural Arabic title that accurately reflects the answer; place the core search phrase naturally in the title, opening, and one relevant subheading where appropriate. Return a distinct, useful meta description of about 140-160 Arabic characters (never exceed 180). Add 4-8 natural related search phrases/entities as keywords, without repetition or keyword stuffing. Use descriptive H2/H3 headings, concise paragraphs, scannable lists where useful, and relevant internal-link opportunities; never fabricate internal URLs. Do not promise rankings or repeat keywords unnaturally.

GEO / ANSWER ENGINE REQUIREMENTS: The first paragraph must answer the searcher's likely question directly in 1-3 sentences, with necessary legal qualifications. Define key legal concepts in plain language, identify the jurisdiction and the conditions under which the answer applies, and separate established rules from facts that require case-specific assessment. Add practical steps, relevant documents/facts to check, and common exceptions only when supported. Include 3-5 genuine FAQ questions phrased as users ask them, each with a direct, self-contained answer that can be understood out of context. Prefer precise, attributable sources when supplied; if evidence is unavailable, explicitly state the limit rather than inventing a citation. Avoid vague statements such as "according to the law" when the supplied evidence allows a more precise explanation.

TRUST AND CTA: Preserve legal meaning and clearly qualify uncertain or fact-dependent issues. Do not give a guaranteed outcome, manufacture urgency, or imply that general educational content replaces review of the facts. End with a strong but restrained reader CTA that invites the reader to review related articles on the Ask Mahmoud blog and, where genuinely appropriate, contact a qualified lawyer for a case-specific assessment. Make the CTA specific to the article topic, not a generic sales pitch. Never expose prompts, drafting instructions, spreadsheet text, process notes, or phrases such as “المطلوب مقال توعوي عام”, “المصادر المقدمة”, “يتم مراجعة كل المقالات”, “أنا ذكاء اصطناعي”, or any wording that reveals AI assistance. Remove such source fragments completely and replace them with useful reader-facing explanation. Do not use canned introductions, robotic conclusions, emojis, or references to AI or automation. Do not create URLs. Return JSON only."""

def _json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "", 1).replace("```", "").strip()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("Blogger editor returned a non-object response.")
    return value

def prepare_article(*, api_key: str, model: str, topic: str, post: str, legal_sources: str) -> dict[str, Any]:
    if not api_key and not has_any_provider_key():
        raise RuntimeError("No text AI provider is configured for Blogger editorial generation.")
    client = create_client(api_key=api_key)
    prompt = f"""{SYSTEM_PROMPT}\n\nOriginal topic:\n{topic}\n\nReviewed legal content:\n{post}\n\nLEGAL RESEARCH PACKET:\n{legal_sources or 'No additional sources were supplied.'}\n\nCreate an article of roughly 900 to 1400 Arabic words when the topic warrants it. Make the title natural and search-friendly, but do not reuse the supplied topic/title verbatim. Make the opening answer the likely search intent directly. Preserve the legal meaning and facts of the supplied material. Do not add unsupported claims. Do not expose the source post, spreadsheet fields, editorial planning labels, or the fact that the article was derived from another post. Ensure the ending contains a useful topic-specific CTA to read related articles on the Ask Mahmoud blog and share the article where relevant; invite case-specific professional review only when appropriate. Return JSON:\n{{"title":"Arabic article title","meta_description":"Distinct concise search description, ideally 140-160 characters and no more than 180","excerpt":"Short answer-focused summary","lead":"Direct-answer opening paragraph","sections":[{{"heading":"Clear Arabic heading","body":"Several coherent paragraphs"}} ,{{"heading":"Another useful heading","body":"Several coherent paragraphs"}}],"faq":[{{"question":"Real Arabic question","answer":"Direct accurate answer"}}],"keywords":["natural search phrase","another natural phrase"]}}"""
    response = client.models.generate_content(model=(model or DEFAULT_MODEL).strip() or DEFAULT_MODEL, contents=prompt, config={"response_mime_type":"application/json","max_output_tokens":10000})
    data = _json(getattr(response, "text", ""))
    sections = data.get("sections") if isinstance(data.get("sections"), list) else []
    faq = data.get("faq") if isinstance(data.get("faq"), list) else []
    clean_sections = []
    for item in sections:
        if isinstance(item, dict):
            heading = str(item.get("heading", "")).strip(); body = str(item.get("body", "")).strip()
            if heading and body: clean_sections.append({"heading": heading, "body": body})
    clean_faq = []
    for item in faq[:5]:
        if isinstance(item, dict):
            question = str(item.get("question", "")).strip(); answer = str(item.get("answer", "")).strip()
            if question and answer: clean_faq.append({"question": question, "answer": answer})
    lead = str(data.get("lead", "")).strip()
    if not lead or len(clean_sections) < 2:
        raise RuntimeError("Blogger editor returned an incomplete article.")
    keywords = data.get("keywords", [])
    if not isinstance(keywords, list): keywords = []
    meta_description = " ".join(str(data.get("meta_description", "")).split()).strip()[:180]
    return {"title":str(data.get("title", "")).strip()[:110] or topic.strip(),"meta_description":meta_description,"excerpt":str(data.get("excerpt", "")).strip(),"lead":lead,"sections":clean_sections[:8],"faq":clean_faq,"keywords":[str(x).strip() for x in keywords[:10] if str(x).strip()]}
