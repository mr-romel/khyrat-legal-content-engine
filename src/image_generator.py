from __future__ import annotations

import base64
from pathlib import Path

from google import genai


class ImageGenerationError(RuntimeError):
    pass


def create_legal_image(*, topic: str, image_brief: str, output_path: str, api_key: str) -> str:
    """Generate an actual 4:5 editorial image with Gemini 3.1 Flash Image."""
    if not api_key:
        raise ImageGenerationError("GEMINI_API_KEY is missing.")

    prompt = f"""
Create a premium editorial social-media image for an Egyptian lawyer's legal education page.

Topic:
{topic}

Visual concept from the content engine:
{image_brief}

Creative direction:
- Create a real visual scene, not a text card, poster, template, infographic, slide, or quote graphic.
- The visual must immediately communicate the legal problem to an Egyptian audience through people, objects, setting, emotion, and action.
- Prefer realistic Egyptian context when relevant.
- Use one strong focal point and visual storytelling.
- Premium cinematic editorial photography / high-end realistic illustration.
- Sophisticated restrained palette inspired by deep navy, warm gold, white, and neutral tones.
- Composition optimized for Facebook feed, portrait 4:5.
- Leave tasteful negative space around the focal subject.
- NO Arabic text anywhere in the image.
- NO English text, headlines, labels, captions, logos, watermarks, fake quotations, or explanatory paragraphs.
- Do not repeat the topic as text.
- Do not use generic justice scales unless they genuinely help explain the specific topic.
- Do not create a generic lawyer-at-desk image unless that is the actual story.
""".strip()

    try:
        client = genai.Client(api_key=api_key)
        interaction = client.interactions.create(
            model="gemini-3.1-flash-image",
            input=prompt,
            response_format={
                "type": "image",
                "aspect_ratio": "4:5",
                "image_size": "1K",
            },
        )

        image_data = getattr(getattr(interaction, "output_image", None), "data", None)
        if not image_data:
            raise ImageGenerationError(
                f"Gemini did not return an output image: {interaction}"
            )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(base64.b64decode(image_data))
        return str(output)

    except ImageGenerationError:
        raise
    except Exception as exc:
        raise ImageGenerationError(f"Gemini image generation failed: {exc}") from exc
