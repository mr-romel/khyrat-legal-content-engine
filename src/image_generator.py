from __future__ import annotations

import base64
from pathlib import Path

from google import genai


IMAGE_MODEL = "gemini-3.1-flash-image"


class ImageGenerationError(RuntimeError):
    pass


def create_legal_image(
    *,
    topic: str,
    image_brief: str,
    output_path: str,
    api_key: str,
) -> str:

    if not api_key:
        raise ImageGenerationError(
            "GEMINI_API_KEY is missing."
        )

    if not topic.strip():
        raise ImageGenerationError(
            "Topic is empty."
        )

    if not image_brief.strip():
        raise ImageGenerationError(
            "Image brief is empty."
        )

    prompt = f"""
Create a premium editorial visual for an Egyptian legal
education Facebook page.

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
- Do NOT place Arabic text anywhere.
- Do NOT place English text anywhere.
- Do NOT place captions.
- Do NOT place headlines.
- Do NOT place legal explanations inside the image.
- Do NOT place logos.
- Do NOT place watermarks.
- Do NOT place a generic justice scale unless truly relevant.
- Avoid generic "lawyer sitting at desk" imagery unless the topic
  specifically requires it.

VISUAL STORYTELLING:

Show the actual human/legal situation represented by the topic.

Use:
- realistic people
- realistic documents
- authentic environment
- believable body language
- appropriate emotions
- cinematic lighting
- strong focal subject
- natural depth
- premium editorial photography aesthetics

Use an Egyptian context when relevant.

The final image must communicate the problem visually
even without reading the caption.

STYLE:

Premium cinematic realism.
High-end editorial photography.
Natural skin texture.
Realistic materials.
Professional lighting.
Subtle sophisticated color palette.
Deep navy, warm gold, white and neutral tones may appear
naturally, but avoid excessive branding.

COMPOSITION:

Portrait 4:5.
Facebook feed optimized.
One clear focal point.
Clean visual hierarchy.
Tasteful negative space.
No clutter.
No collage.
No split screen.
No UI elements.

This image is intended to accompany a serious legal educational post.
It should feel intelligent, credible and emotionally relevant,
not like an AI stock photo.
""".strip()

    try:
        client = genai.Client(
            api_key=api_key
        )

        interaction = client.interactions.create(
            model=IMAGE_MODEL,
            input=prompt,
            response_format={
                "type": "image",
                "mime_type": "image/jpeg",
                "aspect_ratio": "4:5",
                "image_size": "1K",
            },
        )

        output_image = getattr(
            interaction,
            "output_image",
            None,
        )

        image_data = getattr(
            output_image,
            "data",
            None,
        )

        if not image_data:
            raise ImageGenerationError(
                "Gemini did not return image data."
            )

        output = Path(output_path)
        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output.write_bytes(
            base64.b64decode(image_data)
        )

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

        return str(output)

    except ImageGenerationError:
        raise

    except Exception as exc:
        raise ImageGenerationError(
            f"Gemini image generation failed: {exc}"
        ) from exc
