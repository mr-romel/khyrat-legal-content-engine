from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import requests


IMAGE_MODEL = "gemini-3.1-flash-image"
IMAGE_API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


class ImageGenerationError(RuntimeError):
    pass


def _extract_image_base64(payload: dict[str, Any]) -> str:
    """
    Extract generated image data from the current Gemini Interactions
    response structure.

    Google exposes the generated image through output_image.data and
    also through the model_output step content.
    """

    output_image = payload.get("output_image")

    if isinstance(output_image, dict):
        data = output_image.get("data")
        if data:
            return str(data)

    for step in payload.get("steps", []) or []:
        if not isinstance(step, dict):
            continue

        if step.get("type") != "model_output":
            continue

        for block in step.get("content", []) or []:
            if not isinstance(block, dict):
                continue

            if block.get("type") == "image" and block.get("data"):
                return str(block["data"])

    raise ImageGenerationError(
        "Gemini returned a successful response but no image data was found."
    )


def create_legal_image(
    *,
    topic: str,
    image_brief: str,
    output_path: str,
    api_key: str,
) -> str:
    """
    Generate a real 4:5 editorial image using Gemini 3.1 Flash Image.

    Uses the official Gemini Interactions REST endpoint directly.
    This avoids SDK-specific Interactions schema incompatibilities.
    """

    if not api_key:
        raise ImageGenerationError(
            "GEMINI_API_KEY is missing."
        )

    topic = (topic or "").strip()
    image_brief = (image_brief or "").strip()

    if not topic:
        raise ImageGenerationError(
            "Topic is empty."
        )

    if not image_brief:
        raise ImageGenerationError(
            "Image brief is empty."
        )

    prompt = f"""
Create a premium editorial visual for an Egyptian legal education
Facebook page.

SUBJECT:
{topic}

VISUAL BRIEF:
{image_brief}

MANDATORY CREATIVE RULES:

- Create a REAL visual scene.
- Do NOT create a poster.
- Do NOT create an infographic.
- Do NOT create a text card.
- Do NOT create a quote graphic.
- Do NOT reproduce the topic as text.
- Do NOT place Arabic text anywhere in the image.
- Do NOT place English text anywhere in the image.
- Do NOT place captions, headlines or labels.
- Do NOT place legal explanations inside the image.
- Do NOT place logos or watermarks.
- Do NOT use generic justice scales unless they are genuinely relevant.
- Do NOT create a generic lawyer sitting at a desk unless the topic
  specifically requires that scene.

VISUAL STORYTELLING:

Show the actual human/legal situation represented by the subject.

Use realistic people, documents, objects, environments, body language
and emotions appropriate to Egypt when relevant.

The image should visually communicate the problem even without reading
the post.

STYLE:

Premium cinematic realism.
High-end editorial photography.
Realistic skin, clothing, materials and lighting.
Professional art direction.
Sophisticated restrained palette.
Natural deep navy, warm gold, white and neutral tones may appear subtly.

COMPOSITION:

Portrait 4:5.
Optimized for Facebook feed.
One strong focal point.
Clear visual hierarchy.
Natural depth of field.
Tasteful negative space.
No collage.
No split screen.
No UI elements.
No decorative text.

The result must look like an intentionally art-directed professional
editorial image, NOT generic AI stock photography.
""".strip()

    request_body = {
        "model": IMAGE_MODEL,
        "input": [
            {
                "type": "text",
                "text": prompt,
            }
        ],
        "response_format": {
            "type": "image",
            "mime_type": "image/jpeg",
            "aspect_ratio": "4:5",
            "image_size": "1K",
        },
    }

    try:
        response = requests.post(
            IMAGE_API_URL,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=180,
        )
    except requests.RequestException as exc:
        raise ImageGenerationError(
            f"Gemini image network request failed: {exc}"
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ImageGenerationError(
            f"Gemini image API returned non-JSON response "
            f"(HTTP {response.status_code})."
        ) from exc

    if not response.ok:
        error = payload.get("error", {})
        message = error.get(
            "message",
            "Unknown Gemini image API error.",
        )
        code = error.get("code")
        status = error.get("status")

        raise ImageGenerationError(
            f"Gemini image API failed: {message} "
            f"(HTTP {response.status_code}, code={code}, status={status})"
        )

    try:
        image_base64 = _extract_image_base64(payload)

        image_bytes = base64.b64decode(
            image_base64,
            validate=True,
        )
    except ImageGenerationError:
        raise
    except Exception as exc:
        raise ImageGenerationError(
            f"Gemini returned invalid image data: {exc}"
        ) from exc

    output = Path(output_path)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_bytes(image_bytes)

    if (
        not output.exists()
        or output.stat().st_size == 0
    ):
        raise ImageGenerationError(
            "Generated image file is empty."
        )

    print(
        f"AI image generated successfully: {output}"
    )
    print(
        f"Generated image size: {output.stat().st_size} bytes"
    )

    return str(output)
