from __future__ import annotations

import os
import re
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




def create_contextual_fallback_image(*, post_context: str, image_brief: str, output_path: str) -> str:
    """Guaranteed local visual fallback derived from the actual post."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1200, 1500), (18, 25, 38))
    draw = ImageDraw.Draw(image, "RGBA")
    regular_path = "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"
    bold_path = "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"
    regular = ImageFont.truetype(regular_path, 42) if Path(regular_path).exists() else ImageFont.load_default()
    bold = ImageFont.truetype(bold_path, 66) if Path(bold_path).exists() else regular
    text = " ".join(str(post_context or "").split()) or " ".join(str(image_brief or "").split())
    sentences = [s.strip() for s in re.split(r"(?<=[؟!.])\s+", text) if s.strip()]
    scene = (sentences[0] if sentences else text[:420])[:420]
    words = scene.split()
    lines = [" ".join(words[i:i+8]) for i in range(0, len(words), 8)]
    draw.rounded_rectangle((70, 70, 1130, 1430), radius=55, fill=(28, 39, 58, 255), outline=(215, 220, 230, 220), width=4)
    draw.rounded_rectangle((170, 220, 1030, 900), radius=35, fill=(245, 242, 232, 255))
    draw.rectangle((245, 300, 955, 360), fill=(35, 45, 58, 255))
    for y in range(430, 790, 80):
        draw.rounded_rectangle((245, y, 900, y + 18), radius=8, fill=(125, 132, 142, 180))
    draw.ellipse((430, 770, 770, 1110), fill=(45, 105, 155, 210), outline=(230, 235, 240, 240), width=5)
    draw.line((600, 1110, 600, 1260), fill=(230, 235, 240, 230), width=10)
    y = 1180
    for idx, line in enumerate(lines[:4]):
        draw.text((600, y), _rtl_text(line), font=bold if idx == 0 else regular, anchor="mm", fill=(245, 245, 245, 255))
        y += 62
    image.save(path, quality=94, optimize=True)
    return str(path)


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

    account_id = (cloudflare_account_id or "").strip()
    api_token = (cloudflare_api_token or "").strip()
    gemini_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()

    topic = (topic or "").strip()
    image_brief = (image_brief or "").strip()
    post_context = (post_context or "").strip()

    if not topic:
        raise ImageGenerationError("Topic is empty.")
    if not image_brief:
        raise ImageGenerationError("Image brief is empty.")
    if not post_context:
        raise ImageGenerationError("Published post context is required for contextual image generation.")

    # Primary provider: Cloudflare. If it fails, use Gemini native image generation.
    def _generate_with_gemini() -> bytes:
        if not gemini_key:
            raise ImageGenerationError("GEMINI_API_KEY is missing for image fallback.")
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=gemini_key)
            model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
            response = client.models.generate_content(
                model=model, contents=[prompt],
                config=types.GenerateContentConfig(response_modalities=["IMAGE"], response_format={"image": {"aspect_ratio": "4:5"}}),
            )
            for part in getattr(response, "parts", []) or []:
                image = part.as_image() if hasattr(part, "as_image") else None
                if image is not None:
                    import io
                    buf = io.BytesIO()
                    image.save(buf, format="PNG")
                    return buf.getvalue()
            raise ImageGenerationError("Gemini image response contained no image data.")
        except Exception as exc:
            raise ImageGenerationError(f"Gemini image fallback failed: {exc}") from exc
    endpoint = CLOUDFLARE_IMAGE_ENDPOINT.format(account_id=account_id) if account_id and api_token else ""

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

    cloudflare_error = None
    if not endpoint:
        cloudflare_error = "Cloudflare credentials unavailable; using Gemini contextual image generation."
    else:
        try:
            response = requests.post(endpoint, headers=headers, json=request_body, timeout=180)
            if response.ok:
                image_bytes = _extract_image_bytes(response)
            else:
                try:
                    error_payload = response.json()
                except ValueError:
                    error_payload = response.text
                cloudflare_error = f"HTTP {response.status_code} - {error_payload}"
        except requests.RequestException as exc:
            cloudflare_error = str(exc)

    if cloudflare_error:
        print(f"Cloudflare image provider unavailable; switching to Gemini contextual image generation: {cloudflare_error}")
        try:
            image_bytes = _generate_with_gemini()
            provider = "GEMINI_IMAGE_GENERATION"
        except Exception as gemini_error:
            print(f"Gemini image generation failed; using guaranteed contextual local visual: {gemini_error}")
            return create_contextual_fallback_image(
                post_context=post_context,
                image_brief=image_brief,
                output_path=output_path,
            )
    else:
        provider = "DIRECT_CLOUDFLARE"

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

    print(f"Editorial image generated successfully: provider={provider} path={output}")

    print(
        f"Generated image size: "
        f"{output.stat().st_size} bytes"
    )

    return str(output)
