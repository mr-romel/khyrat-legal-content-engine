from __future__ import annotations

import base64
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

MAX_PROMPT_LENGTH = 1800


class ImageGenerationError(RuntimeError):
    """Raised when Cloudflare image generation fails."""


def _extract_image_bytes(
    response: requests.Response,
) -> bytes:
    content_type = (
        response.headers.get("content-type", "")
        .lower()
    )

    if content_type.startswith("image/"):
        if not response.content:
            raise ImageGenerationError(
                "Cloudflare returned an empty image response."
            )
        return response.content

    try:
        payload: dict[str, Any] = response.json()
    except ValueError as exc:
        raise ImageGenerationError(
            "Cloudflare returned neither an image nor valid JSON."
        ) from exc

    if not payload.get("success", False):
        raise ImageGenerationError(
            "Cloudflare AI request failed: "
            f"{payload.get('errors') or payload}"
        )

    result = payload.get("result")
    image_base64: str | None = None

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


def _build_prompt(
    topic: str,
    image_brief: str,
) -> str:
    topic = (
        topic.strip()
        .replace("\r", " ")
        .replace("\n", " ")
    )

    brief = (
        image_brief.strip()
        .replace("\r", " ")
        .replace("\n\n", "\n")
    )

    # Keep a large safety margin below Cloudflare's 2048-char limit.
    if len(brief) > 900:
        brief = (
            brief[:900]
            .rsplit(" ", 1)[0]
            .strip()
        )

    prompt = f"""
Create one realistic cinematic editorial photograph.

LEGAL STORY:
{topic}

VISUAL DIRECTOR BRIEF:
{brief}

Depict the exact human/legal situation described above.
Show the people, their action, the important document or object,
the setting, and the emotional tension.

Use realistic Egyptian context when appropriate.
Professional documentary/editorial photography.
Photorealistic people and materials.
Natural expressions and body language.
Strong focal subject.
Realistic cinematic lighting.
Natural depth of field.
Portrait-friendly composition.

The viewer should understand the situation from the image itself.

ABSOLUTELY NO:
text, Arabic letters, English letters, readable writing,
headlines, captions, typography, logos, watermarks,
poster, infographic, presentation, quote card,
social-media template, collage, split screen, UI,
generic lawyer-at-desk scene, generic courthouse,
generic justice scales, random legal symbols,
abstract legal background.

Do not create a generic legal image.
Depict the actual story.
""".strip()

    if len(prompt) > MAX_PROMPT_LENGTH:
        prompt = (
            prompt[:MAX_PROMPT_LENGTH]
            .rsplit(" ", 1)[0]
            .strip()
        )

    return prompt


def _convert_to_4x5(
    image_bytes: bytes,
    output_path: Path,
) -> None:
    try:
        image = Image.open(
            BytesIO(image_bytes)
        ).convert("RGB")
    except Exception as exc:
        raise ImageGenerationError(
            f"Could not decode generated image: {exc}"
        ) from exc

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
        cloudflare_account_id or ""
    ).strip()

    api_token = (
        cloudflare_api_token or ""
    ).strip()

    if not account_id:
        raise ImageGenerationError(
            "CLOUDFLARE_ACCOUNT_ID is missing."
        )

    if not api_token:
        raise ImageGenerationError(
            "CLOUDFLARE_API_TOKEN is missing."
        )

    if not topic.strip():
        raise ImageGenerationError(
            "Topic is empty."
        )

    if not image_brief.strip():
        raise ImageGenerationError(
            "Image brief is empty."
        )

    prompt = _build_prompt(
        topic,
        image_brief,
    )

    print(
        f"Cloudflare prompt length: {len(prompt)} characters"
    )

    endpoint = IMAGE_ENDPOINT.format(
        account_id=account_id,
    )

    # IMPORTANT:
    # Only fields supported by the REST schema used here.
    # DO NOT add seed.
    request_body = {
        "prompt": prompt,
        "steps": 8,
    }

    # Hard guard: prove that seed can never be sent.
    if "seed" in request_body:
        raise ImageGenerationError(
            "Internal safety check failed: unsupported 'seed' field."
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
            f"HTTP {response.status_code} - {error_payload}"
        )

    image_bytes = _extract_image_bytes(
        response
    )

    if not image_bytes:
        raise ImageGenerationError(
            "Cloudflare returned empty image bytes."
        )

    output = Path(output_path)

    _convert_to_4x5(
        image_bytes,
        output,
    )

    if (
        not output.exists()
        or output.stat().st_size == 0
    ):
        raise ImageGenerationError(
            "Final image file is empty."
        )

    print(
        "Cloudflare FLUX image generated successfully: "
        f"{output}"
    )

    print(
        f"Final image size: {output.stat().st_size} bytes"
    )

    return str(output)
