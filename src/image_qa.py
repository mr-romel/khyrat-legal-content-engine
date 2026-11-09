from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from PIL import Image

from brand_identity import BRAND_OVERLAY_TEXT, BRAND_OVERLAY_SUBTEXT

DEFAULT_QA_MODEL = os.getenv("KHYRAT_IMAGE_QA_MODEL", "gemini-3.1-flash-lite")
# QA is advisory. Only clearly unusable or materially unrelated images should regenerate.
QA_MIN_COMPOSITION = int(os.getenv("KHYRAT_IMAGE_QA_MIN_COMPOSITION", "55"))
QA_MIN_RELEVANCE = int(os.getenv("KHYRAT_IMAGE_QA_MIN_RELEVANCE", "55"))
QA_MIN_OVERALL = int(os.getenv("KHYRAT_IMAGE_QA_MIN_OVERALL", "60"))
QA_HARD_REJECT_RELEVANCE = int(os.getenv("KHYRAT_IMAGE_QA_HARD_REJECT_RELEVANCE", "5"))
QA_HARD_REJECT_OVERALL = int(os.getenv("KHYRAT_IMAGE_QA_HARD_REJECT_OVERALL", "10"))
QA_HARD_REJECT_COMPOSITION = int(os.getenv("KHYRAT_IMAGE_QA_HARD_REJECT_COMPOSITION", "15"))
QA_MAX_RETRIES = max(1, int(os.getenv("KHYRAT_IMAGE_QA_MAX_RETRIES", "1")))
ALLOWED_BRAND_TEXT = BRAND_OVERLAY_TEXT


class ImageQAError(RuntimeError):
    """Raised when visual QA cannot safely complete."""


def _extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^\`\`\`(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\`\`\`$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ImageQAError(f"Gemini image QA returned invalid JSON: {text[:1200]}")
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ImageQAError(f"Gemini image QA returned malformed JSON: {text[:1200]}") from exc
    if not isinstance(data, dict):
        raise ImageQAError("Gemini image QA response is not an object.")
    return data


def _hard_checks(image_path: Path) -> dict[str, Any]:
    try:
        with Image.open(image_path) as image:
            width, height = image.size
            ratio = width / height if height else 0
    except Exception as exc:
        raise ImageQAError(f"Could not open generated image for QA: {exc}") from exc

    is_reel_portrait = width > 0 and height > 0 and abs(ratio - (9 / 16)) <= 0.003
    is_feed_portrait = width > 0 and height > 0 and abs(ratio - 0.8) <= 0.003
    ratio_ok = is_reel_portrait or is_feed_portrait
    ratio_label = "9:16 Reel portrait" if is_reel_portrait else "4:5 feed portrait" if is_feed_portrait else f"actual ratio {width}:{height}"
    return {
        "width": width,
        "height": height,
        "aspect_ratio": round(ratio, 5),
        "aspect_ratio_ok": ratio_ok,
        "aspect_ratio_label": ratio_label,
    }


def _normalize_score(value: Any, fallback: int = 0) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return fallback


def _build_prompt(topic: str, image_brief: str, hard: dict[str, Any], reference_count: int, image_mode: str) -> str:
    # Older callers/tests may provide dimensions without the derived label.
    aspect_ratio_label = hard.get("aspect_ratio_label") or (
        "9:16 Reel portrait" if hard.get("height") and abs((hard.get("width", 0) / hard["height"]) - (9 / 16)) <= 0.003
        else "4:5 feed portrait" if hard.get("height") and abs((hard.get("width", 0) / hard["height"]) - 0.8) <= 0.003
        else f"actual ratio {hard.get('width', 0)}:{hard.get('height', 0)}"
    )
    return f"""
You are the final visual QA editor for a professional legal-content publishing engine.

Inspect the FINAL rendered image, not the original generation response.

LEGAL TOPIC:
{topic}

ORIGINAL VISUAL BRIEF:
{image_brief}

HARD IMAGE CHECK:
- Final dimensions: {hard['width']}x{hard['height']}
- Target aspect ratio: {aspect_ratio_label} (measured from the final image)
- Local aspect-ratio check: {'PASS' if hard['aspect_ratio_ok'] else 'FAIL'}
- Image mode: CONTEXT_ONLY
- Character reference images: none

REFERENCE IMAGE RULE:
No character-reference images are supplied or required. Evaluate the generated scene from the legal topic and visual brief only.
The generated scene must be new and directly communicate the legal situation without relying on a recurring-person identity.

LEGAL RELEVANCE RULE:
Judge the image by whether it clearly and accurately represents the specific legal problem, action, evidence, document, or consequence described in the post and visual brief. Do not impose an unrequested country, nationality, culture, historical period, art style, gender, or cast restriction. Any visual style or setting is acceptable when it is materially relevant to the legal issue and not misleading. Reject generic legal clichés or unrelated decorative imagery when they fail to explain the actual issue.

BRAND OVERLAY RULE:
A small bottom overlay reading "{ALLOWED_BRAND_TEXT}" and "{BRAND_OVERLAY_SUBTEXT}" is intentionally
added by the code after generation. This exact overlay is ALLOWED and must NOT be counted as bad generated text. No platform-specific icon is used.
Any other visible generated text, fake Arabic/English lettering, gibberish, watermark, logo, headline,
caption, sign, document writing, or typography is a defect.

CHECK THESE FIVE THINGS:
1. LEGAL RELEVANCE: Does the image clearly represent the specific legal problem, evidence, action, or consequence described in the post?
2. COMPOSITION: Is the visual clean and professionally composed for the measured {aspect_ratio_label} publishing format?
   Is the focal subject visible? Is the crop safe? Are important hands, faces, documents, and actions
   not awkwardly cut? Is there enough visual breathing room? Is the scene understandable without text?
3. GENERATED TEXT: Detect prominent or legible text generated by the image model. Ignore the intentional
   bottom-right brand overlay described above. Text on papers/screens that are deliberately blurred or too small
   to read is not a defect. Mark text_detected=true only when invented writing is clearly visible and distracts
   from or damages the image.
4. ANATOMY AND VISUAL INTEGRITY: Inspect visible people and objects at normal social-feed viewing size.
   Reject only clear, material defects a viewer would readily notice, such as a visibly fused limb, impossible
   hand shape, duplicated major object, or broken geometry. Do not magnify or speculate about tiny details,
   reflections, shadows, or ambiguous artifacts. If the scene is a still life with no people, do not invent
   anatomy findings.
DECISION:
PASS when the image is usable for publication and materially related to the topic.
REGENERATE only when the scene is materially unrelated, visibly distorted, anatomically implausible, contains duplicated/fused objects, is unusable, or contains generated text that damages the asset.
Do not reject a valid 9:16 Reel image for not being 4:5; use the measured target format above.
Do not invent negative constraints or missing mandatory props. The absence of a person, lawyer, courtroom, justice scales, or any illustrative prop is NOT a defect unless the supplied visual brief explicitly makes that exact element essential. Do not demand generic legal symbols. Judge whether the actual scene communicates the stated legal issue, not whether it matches an imagined stock-photo template.
Do not reject solely for advisory scores or minor aesthetic imperfections when the image is coherent, readable, and materially relevant.
A clearly visible, material anatomy or geometry defect is a valid rejection reason; ambiguous reflections, tiny artifacts, and speculative defects are not.
Do not reject a clean, coherent image merely because composition or styling is not perfect.
The image is a first-class publishing asset; do not publish a visibly malformed image just to avoid another generation attempt.

Return JSON only:
{{
  "decision": "PASS|REGENERATE",
  "composition_score": 0,
  "relevance_score": 0,
  "reference_score": 0,
  "overall_score": 0,
  "text_detected": false,
  "detected_text": [],
  "composition_findings": [],
  "relevance_findings": [],
  "reference_findings": [],
  "issues": [],
  "regeneration_prompt": "short English instructions for the next generation attempt"
}}
""".strip()


def qa_image(
    *,
    api_key: str,
    image_path: str,
    topic: str,
    image_brief: str,
    model: str | None = None,
    image_mode: str = "CONTEXT_ONLY",
) -> dict[str, Any]:
    path = Path(image_path)
    if not path.is_file():
        raise ImageQAError(f"Image does not exist for QA: {path}")

    hard = _hard_checks(path)
    image_mode = "CONTEXT_ONLY"
    references = []
    # QA is advisory only. A missing QA key or non-ideal aspect ratio must not
    # prevent publication of an otherwise valid generated image.
    if not api_key:
        return {
            "decision": "QA_UNAVAILABLE",
            "composition_score": 100,
            "relevance_score": 0,
            "reference_score": 0,
            "overall_score": 0,
            "text_detected": False,
            "detected_text": [],
            "composition_findings": [],
            "relevance_findings": [],
            "reference_findings": [],
            "issues": ["Visual QA unavailable: no QA API key; image cannot be cleared for publication."],
            "regeneration_prompt": "",
            "hard_checks": hard,
            "image_mode": image_mode,
        }

    contents: list[Any] = [
        _build_prompt(topic, image_brief, hard, len(references), image_mode),
        types.Part.from_bytes(data=path.read_bytes(), mime_type="image/jpeg"),
    ]

    for ref in references:
        try:
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".heic": "image/heic",
                ".heif": "image/heif",
                ".avif": "image/avif",
            }.get(ref.suffix.lower())
            if mime:
                contents.append(types.Part.from_bytes(data=ref.read_bytes(), mime_type=mime))
        except OSError as exc:
            print(f"Image QA reference warning for {ref.name}: {exc}")

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=(model or DEFAULT_QA_MODEL).strip() or DEFAULT_QA_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(max_output_tokens=1400),
        )
        data = _extract_json(getattr(response, "text", ""))
    except Exception as exc:
        return {
            "decision": "QA_UNAVAILABLE",
            "composition_score": 0,
            "relevance_score": 0,
            "reference_score": 0,
            "overall_score": 0,
            "text_detected": False,
            "detected_text": [],
            "composition_findings": [],
            "relevance_findings": [],
            "reference_findings": [],
            "issues": [f"Visual QA unavailable ({type(exc).__name__}); image cannot be cleared for publication."],
            "regeneration_prompt": "",
            "hard_checks": hard,
            "image_mode": image_mode,
        }
    decision = str(data.get("decision", "")).strip().upper()
    if decision not in {"PASS", "REGENERATE"}:
        decision = "REGENERATE"

    data["decision"] = decision
    data["composition_score"] = _normalize_score(data.get("composition_score"))
    data["relevance_score"] = _normalize_score(data.get("relevance_score"))
    data["reference_score"] = 100
    data["overall_score"] = _normalize_score(data.get("overall_score"))
    data["text_detected"] = bool(data.get("text_detected", False))
    for field in ("detected_text", "composition_findings", "relevance_findings", "reference_findings", "issues"):
        value = data.get(field, [])
        if not isinstance(value, list):
            value = [str(value)] if value else []
        data[field] = [str(item).strip() for item in value if str(item).strip()]
    data["regeneration_prompt"] = str(data.get("regeneration_prompt", "")).strip()
    data["hard_checks"] = hard
    data["image_mode"] = image_mode

    # Visual QA gates publication on legal relevance and actual image defects.
    soft_warnings = []
    if not hard["aspect_ratio_ok"]:
        soft_warnings.append(f"Aspect-ratio advisory: expected 4:5, got {hard['width']}x{hard['height']}.")
    if data["composition_score"] < QA_MIN_COMPOSITION:
        soft_warnings.append(f"Composition advisory below {QA_MIN_COMPOSITION}.")
    if data["relevance_score"] < QA_MIN_RELEVANCE:
        soft_warnings.append(f"Relevance advisory below {QA_MIN_RELEVANCE}.")
    if data["overall_score"] < QA_MIN_OVERALL:
        soft_warnings.append(f"Overall advisory below {QA_MIN_OVERALL}.")
    # Keep soft score warnings separate from actionable defects so retry prompts
    # do not amplify advisory scores into invented visual requirements.
    data["advisories"] = soft_warnings
    if data["decision"] != "REGENERATE":
        data["decision"] = "PASS"
    data["issues"] = soft_warnings + data["issues"]

    if data["decision"] == "REGENERATE" and not data["regeneration_prompt"]:
        data["regeneration_prompt"] = ""

    # Attach QA outcome to the generation sidecar so a bad image can be traced
    # to the exact provider, prompt hash, and final file hash.
    provenance_path = path.with_suffix(path.suffix + ".provenance.json")
    if provenance_path.is_file():
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["qa_decision"] = data["decision"]
            provenance["qa_model"] = (model or DEFAULT_QA_MODEL).strip() or DEFAULT_QA_MODEL
            provenance["qa_overall_score"] = data["overall_score"]
            provenance["qa_relevance_score"] = data["relevance_score"]
            provenance["qa_issues"] = data["issues"]
            provenance["qa_checked_image_sha256"] = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
            provenance_path.write_text(
                json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"Image provenance QA update warning: {exc}")

    return data


def summarize_qa(data: dict[str, Any]) -> str:
    issues = data.get("issues") or []
    return " | ".join(str(x).strip() for x in issues if str(x).strip())[:1500]
