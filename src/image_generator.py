from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


CLOUDFLARE_IMAGE_MODEL = (
    "@cf/bytedance/stable-diffusion-xl-lightning"
)

CLOUDFLARE_IMAGE_ENDPOINT = (
    "https://api.cloudflare.com/client/v4/accounts/"
    "{account_id}/ai/run/"
    "@cf/bytedance/stable-diffusion-xl-lightning"
)


class ImageGenerationError(RuntimeError):
    """Raised when Cloudflare cannot generate an image."""


def _extract_image_bytes(
    response: requests.Response,
) -> bytes:
    """
    Cloudflare image model responses are binary image data.
    Handle the normal binary response and fail clearly otherwise.
    """

    content_type = (
        response.headers.get("content-type", "")
        .lower()
    )

    if content_type.startswith("image/"):
        return response.content

    # Defensive fallback in case the API returns JSON with image data.
    try:
        payload: dict[str, Any] = response.json()
    except ValueError as exc:
        raise ImageGenerationError(
            "Cloudflare returned a non-image response "
            f"with content-type: {content_type}"
        ) from exc

    if not payload.get("success", False):
        errors = payload.get("errors", [])
        raise ImageGenerationError(
            f"Cloudflare AI request failed: {errors or payload}"
        )

    result = payload.get("result")

    if isinstance(result, str):
        import base64

        try:
            return base64.b64decode(
                result,
                validate=True,
            )
        except Exception as exc:
            raise ImageGenerationError(
                "Cloudflare returned an invalid base64 image."
            ) from exc

    if isinstance(result, dict):
        image_b64 = result.get("image")

        if image_b64:
            import base64

            try:
                return base64.b64decode(
                    image_b64,
                    validate=True,
                )
            except Exception as exc:
                raise ImageGenerationError(
                    "Cloudflare returned invalid image data."
                ) from exc

    raise ImageGenerationError(
        "Cloudflare response did not contain image data."
    )


def create_legal_image(
    *,
    topic: str,
    image_brief: str,
    output_path: str,
    api_key: str | None = None,
    cloudflare_account_id: str | None = None,
    cloudflare_api_token: str | None = None,
) -> str:
    """
    Generate a real editorial image using Cloudflare Workers AI.

    The image engine is intentionally independent from Gemini so that
    the Core Engine can swap image providers later without redesign.
    """

    del api_key  # Gemini is no longer used for image generation.

    account_id = (
        cloudflare_account_id or ""
    ).strip()

    api_token = (
        cloudflare_api_token or ""
    ).strip()

    topic = (
        topic or ""
    ).strip()

    image_brief = (
        image_brief or ""
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

    prompt = f"""
Create a premium editorial image for an Egyptian legal education page.

SUBJECT:
{topic}

VISUAL BRIEF:
{image_brief}

CREATIVE REQUIREMENTS:

- Real visual storytelling.
- Photorealistic and cinematic.
- Egyptian context where relevant.
- Show the actual human/legal situation.
- One clear focal subject.
- Strong composition.
- Natural human expressions and body language.
- Realistic documents and objects.
- Professional editorial photography aesthetic.
- Serious, credible and sophisticated.
- Optimized for a professional Facebook legal page.
- Portrait composition, 4:5.

ABSOLUTELY DO NOT:
- add text
- add Arabic letters
- add English letters
- add headlines
- add captions
- add legal explanations
- add logos
- add watermarks
- create a poster
- create an infographic
- create a presentation
- create a quote card
- create a social media template
- create a collage
- create a generic lawyer-at-a-desk scene
- use generic justice scales unless specifically relevant

The image must communicate the problem visually without requiring
any text or explanation.
""".strip()

    negative_prompt = """
text, typography, letters, Arabic text, English text,
headline, caption, subtitle, logo, watermark,
poster, infographic, presentation, quote card,
social media template, UI, screenshot, collage,
split screen, generic lawyer desk,
generic scales of justice, cartoon,
cheap stock photo, distorted face,
extra fingers, malformed hands, duplicate people,
blurry subject, low detail, oversaturated
""".strip()

    endpoint = CLOUDFLARE_IMAGE_ENDPOINT.format(
        account_id=account_id,
    )

    # 4:5 portrait.
    width = 768
    height = 960

    request_body = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "num_steps": 8,
        "guidance": 7.5,
    }

    headers = {
        "Authorization": (
            f"Bearer {api_token}"
        ),
        "Content-Type": "application/json",
        "Accept": "image/*",
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

    image_bytes = _extract_image_bytes(
        response
    )

    output = Path(
        output_path
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_bytes(
        image_bytes
    )

    if (
        not output.exists()
        or output.stat().st_size == 0
    ):
        raise ImageGenerationError(
            "Generated image file is empty."
        )

    print(
        "Cloudflare AI image generated successfully: "
        f"{output}"
    )

    print(
        f"Generated image size: "
        f"{output.stat().st_size} bytes"
    )

    return str(output)
