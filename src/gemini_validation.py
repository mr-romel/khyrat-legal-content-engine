from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("Gemini did not return a valid JSON object. Raw response: " + text[:2000])
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini returned invalid JSON. Raw response: " + text[:2000]) from exc
    if not isinstance(data, dict):
        raise RuntimeError("Gemini JSON response is not an object.")
    return data


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    value = str(value).strip()
    return [value] if value else []


def normalize_review_level(value: Any) -> str:
    level = str(value or "").strip().upper()
    return level if level in {"CLEAR", "REVIEW", "BLOCK"} else "REVIEW"


def validate_image_brief(image_brief: str) -> None:
    brief = image_brief.strip().lower()
    if not brief:
        raise RuntimeError("Gemini returned an empty image_brief.")
    generic_phrases = [
        "professional legal image", "professional law image", "legal background",
        "lawyer in office", "lawyer at desk", "justice scales", "legal documents",
        "legal themed image", "legal concept", "professional legal scene",
    ]
    matched = [phrase for phrase in generic_phrases if phrase in brief]
    if matched:
        raise RuntimeError("Gemini returned a generic image brief: " + str(matched))
    detail_markers = [
        "person", "people", "man", "woman", "document", "paper", "room", "office",
        "street", "hands", "expression", "body language", "camera", "lighting",
        "close-up", "medium shot", "background",
    ]
    detail_count = sum(1 for marker in detail_markers if marker in brief)
    if detail_count < 3:
        raise RuntimeError("Gemini image_brief is too generic.")
