from __future__ import annotations

import json
from typing import Any
from google import genai

DEFAULT_MODEL = "gemini-3.6-flash"
SYSTEM_PROMPT = """You are the senior Egyptian legal editor for Ask Mahmoud. Turn a reviewed social post into an original, human-sounding Arabic web article. Write in professional Egyptian Arabic with natural variation, as if written by an Egyptian lawyer with real practice experience. The reader comes first. Improve search discoverability and answer-engine comprehension without keyword stuffing. Use Egypt and Egyptian law only when supported by the supplied material. Never invent a statute number, penalty, ruling, deadline, procedure, exception, fact, or source. The first paragraph must answer the searcher's likely question directly. Explain practical consequences and what facts or documents matter. Use useful subheadings and include 3 to 5 real FAQ questions with direct answers. Do not use canned introductions, robotic conclusions, sales language, emojis, or references to AI or automation. Do not create URLs. Return JSON only."""

def _json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "", 1).replace("```", "").strip()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("Blogger editor returned a non-object response.")
    return value

def prepare_article(*, api_key: str, model: str, topic: str, post: str, legal_sources: str) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing for Blogger editorial generation.")
    client = genai.Client(api_key=api_key)
    prompt = f"""{SYSTEM_PROMPT}\n\nOriginal topic:\n{topic}\n\nReviewed legal content:\n{post}\n\nLegal sources:\n{legal_sources or 'No additional sources were supplied.'}\n\nCreate an article of roughly 900 to 1400 Arabic words when the topic warrants it. Make the title natural and search-friendly. Make the opening answer the likely search intent directly. Preserve the legal meaning and facts of the supplied material. Do not add unsupported claims.\n\nReturn JSON:\n{{\"title\":\"Arabic article title\",\"meta_description\":\"Natural concise description\",\"excerpt\":\"Short summary\",\"lead\":\"Direct-answer opening paragraph\",\"sections\":[{{\"heading\":\"Clear Arabic heading\",\"body\":\"Several coherent paragraphs\"}},{{\"heading\":\"Another useful heading\",\"body\":\"Several coherent paragraphs\"}}],\"faq\":[{{\"question\":\"Real Arabic question\",\"answer\":\"Direct accurate answer\"}}],\"keywords\":[\"natural search phrase\",\"another natural phrase\"]}}"""
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
    return {"title":str(data.get("title", "")).strip()[:110] or topic.strip(),"meta_description":str(data.get("meta_description", "")).strip()[:180],"excerpt":str(data.get("excerpt", "")).strip(),"lead":lead,"sections":clean_sections[:8],"faq":clean_faq,"keywords":[str(x).strip() for x in keywords[:10] if str(x).strip()]}
