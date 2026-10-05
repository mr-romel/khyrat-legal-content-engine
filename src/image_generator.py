from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display


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


def _rtl_text(text: str) -> str:
    return get_display(arabic_reshaper.reshape(str(text or "")))


def brand_published_image(image_path: str) -> str:
    """Apply the mandatory Ask Mahmoud brand mark to every published image."""
    path = Path(image_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ImageGenerationError("Cannot brand a missing image.")

    try:
        image = Image.open(path).convert("RGB")
        width, height = image.size
        draw = ImageDraw.Draw(image, "RGBA")

        bold_path = "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"
        bold = ImageFont.truetype(bold_path, max(28, int(width * 0.038)))

        strip_h = max(92, int(height * 0.115))
        y0 = height - strip_h
        draw.rectangle((0, y0, width, height), fill=(8, 16, 30, 215))

        radius = max(22, int(strip_h * 0.27))
        cx = max(radius + 18, int(width * 0.075))
        cy = y0 + strip_h // 2
        fb_blue = (24, 119, 242, 255)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=fb_blue)

        f_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            max(26, int(radius * 1.35)),
        )
        f_bbox = draw.textbbox((0, 0), "f", font=f_font)
        fw, fh = f_bbox[2] - f_bbox[0], f_bbox[3] - f_bbox[1]
        draw.text(
            (cx - fw / 2, cy - fh / 2 - max(2, int(radius * 0.10))),
            "f", font=f_font, fill=(255, 255, 255, 255)
        )

        brand = _rtl_text("اسأل محمود - مستشار قانوني للشركات")
        bbox = draw.textbbox((0, 0), brand, font=bold)
        tw = bbox[2] - bbox[0]
        if cx + radius + 18 + tw > width - 18:
            bold = ImageFont.truetype(bold_path, max(18, int(width * 0.028)))
            bbox = draw.textbbox((0, 0), brand, font=bold)
            tw = bbox[2] - bbox[0]

        draw.text(
            (width - 18 - tw, cy - (bbox[3] - bbox[1]) / 2),
            brand, font=bold, fill=(255, 255, 255, 255)
        )

        image.save(path, quality=94, optimize=True)
        return str(path)
    except Exception as exc:
        raise ImageGenerationError(
            f"Failed to apply mandatory image branding: {exc}"
        ) from exc


def create_legal_image(
    *,
    topic: str,
    image_brief: str,
    output_path: str,
    post_context: str = "",
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

    post_context = (
        post_context or ""
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

    # The published post is the visual source of truth. The spreadsheet topic is
    # metadata only and must never override the concrete situation described in
    # the actual post.
    prompt = f"""
Create a premium editorial photograph that visually explains the ACTUAL LEGAL SITUATION described in the published Egyptian Arabic post below.

PUBLISHED POST — PRIMARY VISUAL SOURCE:
{post_context or "No post supplied."}

EXTRACTED VISUAL BRIEF:
{image_brief}

METADATA ONLY — DO NOT VISUALIZE THIS AS A GENERIC SUBJECT:
{topic}

SCENE EXTRACTION RULES:
- Read the published post first and extract ONE concrete, visually representable moment, action, object, document, interaction, workplace situation, family situation, property situation, financial transaction, or procedural event explicitly described in it
- The published post has priority over the metadata topic and over any generic legal imagery
- Build the image around that exact moment from the post, not around the broad legal category
- If the post describes a person receiving, signing, refusing, sending, reviewing, keeping, handing over, terminating, disputing, paying, demanding, or discussing a specific thing, show that exact action and thing
- If the post describes a document, contract, cheque, receipt, notice, employment paper, lease, complaint, evidence, phone message, payment, or other concrete item, make that item central to the composition
- If the post describes a dispute between people, show the actual relationship and interaction described, with realistic body language
- If the post describes a company or workplace decision, show the actual decision context rather than a generic lawyer portrait
- Do NOT invent a different incident merely because it is more visually attractive
- Do NOT replace the post's concrete situation with a courthouse, gavel, scales of justice, law books, a lawyer at a desk, or an abstract legal background unless the post itself is specifically about that scene
- The image must be understandable as an illustration of THIS POST even if the viewer never sees the topic field or any caption
- Do not put legal text, explanations, labels, or invented facts into the image
- Prefer a realistic Egyptian setting when the post supports it

CREATIVE REQUIREMENTS:
- Photorealistic cinematic editorial photography
- One unmistakable focal situation
- Natural Egyptian people, clothing, interiors, streets, offices, homes, or workplaces where relevant
- Realistic documents and objects, but all written content must be unreadable/non-textual
- Strong composition and clear action
- Serious, credible, sophisticated professional photography
- Portrait composition, 4:5

ABSOLUTELY DO NOT:
- add text, letters, Arabic writing, English writing, numbers, headlines, captions, subtitles
- add logos or watermarks
- create a poster, infographic, presentation, quote card, social template, collage, UI, or screenshot
- create a generic lawyer-at-a-desk scene
- create generic justice scales or courthouse imagery unless the post explicitly describes them
- create an unrelated stock-photo concept
- invent a legal event that does not appear in the post

The final image must be a direct visual translation of the published post's concrete situation.
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
ancient Egypt, pharaoh, ancient costume, historical reenactment, fantasy,
blurry subject, low detail, oversaturated
""".strip()

    endpoint = CLOUDFLARE_IMAGE_ENDPOINT.format(
        account_id=account_id,
    )

    # 4:5 portrait. Keep enough diffusion steps for a coherent real-world scene.
    width = 1024
    height = 1280
    try:
        num_steps = max(8, min(int(os.environ.get("CLOUDFLARE_IMAGE_STEPS", "25")), 30))
    except ValueError:
        num_steps = 25
    try:
        guidance = float(os.environ.get("CLOUDFLARE_IMAGE_GUIDANCE", "6.0"))
    except ValueError:
        guidance = 6.0

    request_body = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "num_steps": num_steps,
        "guidance": guidance,
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
