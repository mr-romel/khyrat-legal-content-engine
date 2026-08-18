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
    """Generate a real 4:5 editorial image with Gemini Image generation."""

    if not api_key:
        raise ImageGenerationError("GEMINI_API_KEY is missing.")

    if not topic.strip():
        raise ImageGenerationError("Topic is empty.")

    if not image_brief.strip():
        raise ImageGenerationError("Image brief is empty.")

    prompt = f"""
Create a premium editorial social-media image for an Egyptian legal
education page.

TOPIC:
{topic}

VISUAL CONCEPT:
{image_brief}

FINAL CREATIVE DIRECTION:
- Real visual storytelling, NOT a text card.
- NOT a poster.
- NOT an infographic.
- NOT a presentation slide.
- NOT a quote graphic.
- Show the legal problem through a believable scene.
- Use realistic Egyptian people, environments, documents and objects
  when relevant to the subject.
- One strong focal point.
- Natural human expressions and body language.
- Sophisticated editorial photography.
- Premium cinematic realism.
- Professional composition suitable for a lawyer's Facebook page.
- Portrait composition, 4:5.
- Strong depth, realistic lighting and believable materials.
- Leave some clean negative space naturally around the main subject.
- NO Arabic text anywhere.
- NO English text anywhere.
- NO headlines.
- NO captions.
- NO explanatory text.
- NO logos.
- NO watermarks.
- NO fake legal quotations.
- NO generic justice scales unless they are genuinely relevant.
- Do not depict an irrelevant generic lawyer at a desk.
- The image must communicate the problem visually without requiring text.
""".strip()

    try:
        client = genai.Client(api_key=api_key)

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

        output_image = getattr(interaction, "output_image", None)
        image_data = getattr(output_image, "data", None)

        if not image_data:
            raise ImageGenerationError(
                "Gemini did not return image data."
            )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        output.write_bytes(base64.b64decode(image_data))

        if not output.is_file() or output.stat().st_size == 0:
            raise ImageGenerationError(
                "Image file was not created correctly."
            )

        return str(output)

    except ImageGenerationError:
        raise

    except Exception as exc:
        raise ImageGenerationError(
            f"Gemini image generation failed: {exc}"
        ) from exc
