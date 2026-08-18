from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageOps


IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"

IMAGE_ENDPOINT = (
    "https://api.cloudflare.com/client/v4/accounts/"
    "{account_id}/ai/run/"
    "@cf/black-forest-labs/flux-1-schnell"
)


class ImageGenerationError(RuntimeError):
    """Raised when image generation fails."""


def _make_seed(topic: str) -> int:
    """
    Create a deterministic seed from the topic.

    Same topic -> same seed.
    Different topic -> different seed.
    """
    digest = hashlib.sha256(
        topic.encode("utf-8")
    ).hexdigest()

    return int(digest[:8], 16)


def _extract_base64_image(
    response: requests.Response,
) -> bytes:

    content_type = (
        response.headers.get(
            "content-type",
            "",
        )
        .lower()
    )

    # Some Cloudflare responses may be returned directly
    # as binary image data.
    if content_type.startswith("image/"):
        if response.content:
            return response.content

    try:
        payload: dict[str, Any] = response.json()

    except ValueError as exc:
        raise ImageGenerationError(
            "Cloudflare returned a non-JSON, non-image response."
        ) from exc

    if not payload.get("success", False):
        raise ImageGenerationError(
            "Cloudflare AI request failed: "
            f"{payload.get('errors') or payload}"
        )

    result = payload.get("result")

    image_base64 = None

    if isinstance(result, dict):
        image_base64 = result.get("image")

    elif isinstance(result, str):
        image_base64 = result

    if not image_base64:
        raise ImageGenerationError(
            "Cloudflare returned no image data."
        )

    try:
        return base64.b64decode(
            image_base64,
            validate=True,
        )

    except Exception as exc:
        raise ImageGenerationError(
            "Cloudflare returned invalid Base64 image data."
        ) from exc


def _convert_to_4x5(
    image_bytes: bytes,
    output_path: Path,
) -> None:
    """
    FLUX Schnell commonly returns a landscape image.
    We convert it into a professional 4:5 portrait crop.

    The crop is centered slightly above the middle because
    human faces and focal subjects are commonly positioned
    in the upper-middle composition.
    """

    try:
        image = Image.open(
            BytesIO(image_bytes)
        ).convert("RGB")

    except Exception as exc:
        raise ImageGenerationError(
            f"Could not decode generated image: {exc}"
        ) from exc

    target_ratio = 4 / 5
    source_ratio = image.width / image.height

    if abs(source_ratio - target_ratio) < 0.02:
        final_image = image

    else:
        # ImageOps.fit performs a high-quality cover crop.
        final_image = ImageOps.fit(
            image,
            (1024, 1280),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.43),
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    final_image.save(
        output_path,
        format="JPEG",
        quality=94,
        optimize=True,
    )


def create_legal_image(
    *,
    topic: str,
    image_brief: str,
    output_path: str,
    cloudflare_account_id: str | None = None,
    cloudflare_api_token: str | None = None,
) -> str:

    account_id = (
        cloudflare_account_id
        or ""
    ).strip()

    api_token = (
        cloudflare_api_token
        or ""
    ).strip()

    topic = (
        topic
        or ""
    ).strip()

    image_brief = (
        image_brief
        or ""
    ).strip()

    if not account_id:
        raise ImageGenerationError(
            "CLOUDFLARE_ACCOUNT_ID is missing."
        )

    if not api_token:
        raise ImageGenerationError(
            "CLOUDFLARE_API_TOKEN is missing."
        )

    if not topic:
        raise ImageGenerationError(
            "Topic is empty."
        )

    if not image_brief:
        raise ImageGenerationError(
            "Image brief is empty."
        )

    # ------------------------------------------------------------
    # IMPORTANT:
    # We are deliberately NOT asking FLUX for a generic
    # "legal image".
    #
    # We force it to depict the actual story.
    # ------------------------------------------------------------

    prompt = f"""
EDITORIAL LEGAL STORY IMAGE

Create ONE highly specific cinematic editorial photograph
that visually depicts the exact legal problem described below.

LEGAL TOPIC:
{topic}

VISUAL DIRECTOR'S BRIEF:
{image_brief}

CORE OBJECTIVE:
A person should understand the situation from the image alone,
without reading the caption.

SCENE REQUIREMENTS:

- Depict a specific real-life event, not an abstract concept.
- Show the people involved in the actual problem.
- Show what they are physically doing.
- Show the important object/document involved.
- Show the emotional tension appropriate to the situation.
- Use a realistic Egyptian setting whenever the subject naturally
  requires an Egyptian context.
- The image must feel like a moment captured from a real story.

CAMERA:

Professional editorial photography.
Medium shot or medium close-up when useful.
Strong focal subject.
Natural depth of field.
Subtle cinematic lighting.
Realistic skin and clothing.
Natural hands and body language.
Believable environment.

LEGAL STORYTELLING:

The central object or action must correspond directly to the topic.

Do not replace the actual story with generic legal symbolism.

For example:
If the subject concerns a trust receipt, visually show
people handling/signing/handing over the relevant document
in a realistic dispute-related situation.

If the subject concerns an employment termination,
visually show an employee receiving a termination document
inside a realistic workplace.

If the subject concerns a contract,
visually show a person reviewing or signing a contract
with attention to the relevant clause.

These are principles, not instructions to copy those examples.

VISUAL PRIORITY:

1. Actual human/legal situation.
2. Important document/object.
3. Human emotion.
4. Environment.
5. Cinematic composition.

STRICT NEGATIVE RULES:

NO Arabic text.
NO English text.
NO readable writing.
NO headline.
NO caption.
NO typography.
NO logo.
NO watermark.
NO poster.
NO infographic.
NO presentation slide.
NO quote card.
NO social-media template.
NO collage.
NO split screen.
NO generic courthouse.
NO generic scales of justice.
NO floating legal icons.
NO random books.
NO generic lawyer sitting at a desk.
NO abstract blue legal background.
NO stock-photo composition.
NO unrelated objects.

The result must NOT look like an AI-generated social media graphic.

It should look like:
a premium editorial photograph from a serious Egyptian legal
journalism or documentary story.

Portrait-oriented composition is preferred.
Keep the primary subject near the center.
Avoid placing the key subject at the extreme left or right
because the final image will be cropped to a 4:5 portrait composition.

FINAL IMAGE:
photorealistic, cinematic, credible, emotionally clear,
professionally art-directed, realistic Egyptian context,
single coherent scene.
""".strip()

    seed = _make_seed(topic)

    request_body = {
        "prompt": prompt,
        "steps": 8,
        "seed": seed,
    }

    endpoint = IMAGE_ENDPOINT.format(
        account_id=account_id,
    )

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=request_body,
            timeout=180,
        )

    except requests.RequestException as exc:
        raise ImageGenerationError(
            f"Cloudflare image request failed: {exc}"
        ) from exc

    if not response.ok:
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = response.text

        raise ImageGenerationError(
            "Cloudflare image API failed: "
            f"HTTP {response.status_code} - "
            f"{error_payload}"
        )

    try:
        image_bytes = _extract_base64_image(
            response
        )

    except ImageGenerationError:
        raise

    if not image_bytes:
        raise ImageGenerationError(
            "Cloudflare returned an empty image."
        )

    output = Path(
        output_path
    )

    # ------------------------------------------------------------
    # Convert to final 4:5 JPG
    # ------------------------------------------------------------

    _convert_to_4x5(
        image_bytes,
        output,
    )

    if (
        not output.exists()
        or output.stat().st_size == 0
    ):
        raise ImageGenerationError(
            "Final 4:5 image file is empty."
        )

    print(
        "Cloudflare FLUX image generated successfully:"
        f" {output}"
    )

    print(
        f"Final image size: "
        f"{output.stat().st_size} bytes"
    )

    return str(output)
