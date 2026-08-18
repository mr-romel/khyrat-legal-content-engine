from __future__ import annotations

import base64
from pathlib import Path

from google import genai
from google.genai import types


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
    """
    Generate a real 4:5 editorial image using Gemini 3.1 Flash Image.

    This implementation uses the stable generate_content API instead
    of the experimental Interactions API.
    """

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
- Do NOT place generic justice scales unless genuinely relevant.
- Do NOT create generic "lawyer at desk" imagery unless the topic
  specifically requires it.

VISUAL STORYTELLING:

Show the actual human/legal situation represented by the topic.

Use realistic:
- Egyptian people when relevant
- documents
- environments
- body language
- facial expressions
- objects
- lighting
- depth
- materials

The image should tell a clear story even without the caption.

STYLE:

Premium cinematic realism.
High-end editorial photography.
Natural skin texture.
Realistic materials.
Professional lighting.
Sophisticated restrained palette.
Deep navy, warm gold, white and neutral tones may appear naturally.

COMPOSITION:

Portrait 4:5.
Optimized for Facebook feed.
One clear focal point.
Strong visual hierarchy.
Tasteful negative space.
No clutter.
No collage.
No split screen.
No UI elements.

The result must feel like an intentionally art-directed
professional legal editorial image, not generic AI stock photography.
""".strip()

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                response_format={
                    "image": {
                        "aspect_ratio": "4:5",
                        "image_size": "1K",
                    }
                },
            ),
        )

        image_part = None

        for part in response.parts or []:
            inline_data = getattr(part, "inline_data", None)

            if inline_data is not None:
                image_part = inline_data
                break

        if image_part is None:
            raise ImageGenerationError(
                "Gemini returned no image part."
            )

        image_data = getattr(
            image_part,
            "data",
            None,
        )

        if not image_data:
            raise ImageGenerationError(
                "Gemini image part contains no data."
            )

        # google-genai normally exposes inline_data.data as bytes,
        # but support base64 strings defensively.
        if isinstance(image_data, bytes):
            decoded = image_data
        elif isinstance(image_data, str):
            try:
                decoded = base64.b64decode(
                    image_data,
                    validate=True,
                )
            except Exception as exc:
                raise ImageGenerationError(
                    "Gemini returned an invalid base64 image."
                ) from exc
        else:
            raise ImageGenerationError(
                "Gemini returned an unsupported image data type."
            )

        output = Path(output_path)
        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output.write_bytes(decoded)

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
            f"Image size: {output.stat().st_size} bytes"
        )

        return str(output)

    except ImageGenerationError:
        raise

    except Exception as exc:
        raise ImageGenerationError(
            f"Gemini image generation failed: {exc}"
        ) from exc
