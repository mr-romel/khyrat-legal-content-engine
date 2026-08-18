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

MAX_PROMPT_LENGTH = 1800


class ImageGenerationError(RuntimeError):
    """Raised when image generation fails."""


def _make_seed(topic: str) -> int:
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

    if content_type.startswith("image/"):
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

    try:
        image = Image.open(
            BytesIO(image_bytes)
        ).convert("RGB")

    except Exception as exc:
        raise ImageGenerationError(
            f"Could not decode generated image: {exc}"
        ) from exc

    target_size = (1024, 1280)

    final_image = ImageOps.fit(
        image,
        target_size,
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


def _build_prompt(
    topic: str,
    image_brief: str,
) -> str:
    """
    Build a compact FLUX prompt that stays safely below
    Cloudflare's 2048-character limit.
    """

    # Keep the Gemini brief, but reserve room for our fixed instructions.
    brief_budget = 950

    compact_brief = (
        image_brief
        .strip()
        .replace("\n\n", "\n")
    )

    if len(compact_brief) > brief_budget:
        compact_brief = (
            compact_brief[:brief_budget]
            .rsplit(" ", 1)[0]
            .strip()
        )

    topic_budget = 220

    compact_topic = topic.strip()

    if len(compact_topic) > topic_budget:
        compact_topic = (
            compact_topic[:topic_budget]
            .rsplit(" ", 1)[0]
            .strip()
        )

    fixed_instruction = """
Create one realistic cinematic editorial photograph.

Story:
{topic}

Visual direction:
{brief}

Show the actual people, action, important object/document,
setting and emotion described above.

Egyptian context when relevant.
Professional documentary/editorial photography.
Natural human expressions and body language.
Strong focal subject.
Portrait-friendly composition, 4:5 crop.
Realistic lighting and materials.

ABSOLUTELY NO:
text, letters, Arabic writing, English writing, headlines,
captions, logos, watermark, poster, infographic, collage,
UI, split screen, generic lawyer-at-desk scene,
generic justice scales, random legal symbols.
""".strip().format(
        topic=compact_topic,
        brief=compact_brief,
    )

    # Final safety guard.
    if len(fixed_instruction) > MAX_PROMPT_LENGTH:
        fixed_instruction = (
            fixed_instruction[:MAX_PROMPT_LENGTH]
            .rsplit(" ", 1)[0]
            .strip()
        )

    return fixed_instruction


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

    request_body = {
        "prompt": prompt,
        "steps": 8,
        "seed": _make_seed(topic),
    }

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

    image_bytes = _extract_base64_image(
        response
    )

    if not image_bytes:
        raise ImageGenerationError(
            "Cloudflare returned an empty image."
        )

    output = Path(
        output_path
    )

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
        "Cloudflare FLUX image generated successfully: "
        f"{output}"
    )

    print(
        f"Final image size: "
        f"{output.stat().st_size} bytes"
    )

    return str(output)
