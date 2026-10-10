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


def _draw_arabic_text(draw, xy, text: str, *, font, fill, anchor=None):
    """Draw Arabic in logical order using Pillow's RTL layout engine when available."""
    options = {"font": font, "fill": fill, "direction": "rtl", "language": "ar"}
    if anchor:
        options["anchor"] = anchor
    try:
        draw.text(xy, str(text or ""), **options)
    except (TypeError, ValueError):
        # Older Pillow builds lack RAQM; reshape/reorder exactly once as fallback.
        fallback = {"font": font, "fill": fill}
        if anchor:
            fallback["anchor"] = anchor
        draw.text(xy, get_display(arabic_reshaper.reshape(str(text or ""))), **fallback)


def brand_published_image(image_path: str) -> str:
    """Apply the mandatory Ask Mahmoud brand mark to every published image."""
    path = Path(image_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ImageGenerationError("Cannot brand a missing image.")

    try:
        image = Image.open(path).convert("RGB")
        width, height = image.size
        draw = ImageDraw.Draw(image, "RGBA")

        font_candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        bold_path = next((p for p in font_candidates if Path(p).exists()), None)
        if bold_path:
            bold = ImageFont.truetype(bold_path, max(28, int(width * 0.038)))
        else:
            bold = ImageFont.load_default()

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

        brand = "اسأل محمود - مستشار قانوني للشركات"
        # Keep logical Arabic text intact for RAQM. On older Pillow builds,
        # shape/reorder once and draw that fallback string without RTL flags.
        display_brand = brand
        use_raqm = True
        try:
            bbox = draw.textbbox((0, 0), brand, font=bold, direction="rtl", language="ar")
        except (TypeError, ValueError):
            use_raqm = False
            display_brand = get_display(arabic_reshaper.reshape(brand))
            bbox = draw.textbbox((0, 0), display_brand, font=bold)
        tw = bbox[2] - bbox[0]
        if cx + radius + 18 + tw > width - 18:
            if bold_path:
                bold = ImageFont.truetype(bold_path, max(18, int(width * 0.028)))
            measure_text = brand if use_raqm else display_brand
            try:
                bbox = draw.textbbox((0, 0), measure_text, font=bold, direction="rtl", language="ar") if use_raqm else draw.textbbox((0, 0), measure_text, font=bold)
            except (TypeError, ValueError):
                use_raqm = False
                display_brand = get_display(arabic_reshaper.reshape(brand))
                bbox = draw.textbbox((0, 0), display_brand, font=bold)
            tw = bbox[2] - bbox[0]

        # Center vertically and align to the right edge; 'rm' is a middle
        # anchor, unlike 'ra' which anchors at the ascender line.
        try:
            if use_raqm:
                draw.text((width - 18, cy), brand, font=bold, fill=(255, 255, 255, 255),
                          anchor="rm", direction="rtl", language="ar")
            else:
                draw.text((width - 18, cy), display_brand, font=bold, fill=(255, 255, 255, 255),
                          anchor="rm")
        except (TypeError, ValueError):
            display_brand = get_display(arabic_reshaper.reshape(brand))
            draw.text((width - 18, cy), display_brand, font=bold, fill=(255, 255, 255, 255))


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
    visual_description: str = "",
    api_key: str | None = None,
    cloudflare_account_id: str | None = None,
    cloudflare_api_token: str | None = None,
) -> str:
    """
    Generate ONE fresh editorial image for every post.

    The image prompt is derived directly from the complete published post.
    No generic topic-only prompt, local placeholder image, or text-only
    publication fallback is allowed.
    """
    account_id = (cloudflare_account_id or "").strip()
    api_token = (cloudflare_api_token or "").strip()
    gemini_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    visual_description = " ".join(str(visual_description or "").split()).strip()
    if not visual_description:
        raise ImageGenerationError("A post-derived visual description is required.")

    # The visual description is already extracted from the final post.
    # The image model must not reinterpret the topic or invent a generic legal scene.
    prompt = (
        "Create exactly the single realistic editorial photograph described below. "
        "The description is derived exclusively from the final social-media post. "
        "Follow its people, action, setting, and visible evidence literally. "
        "Do not replace the described event with generic legal stock imagery. "
        "Egypt means contemporary present-day Egypt, never ancient or pharaonic Egypt. "
        "Strictly exclude pyramids, temples, hieroglyphs, sarcophagi, pharaohs, ancient statues, "
        "ancient costumes, archaeological ruins, papyrus, and historical motifs unless the post is explicitly about antiquities. "
        "Use a modern, plausible setting that is directly supported by the scene description; do not add national stereotypes. "
        "Use realistic people, authentic contemporary environments, natural expressions, "
        "documentary/editorial photography, natural cinematic light, and one clear focal subject. "
        "Do not add courtroom imagery, justice scales, law books, lawyer stock scenes, "
        "or office scenes unless explicitly described below. "
        "No readable text, captions, letters, numbers, logos, watermarks, UI, "
        "infographics, posters, or signage. No cartoon, illustration, 3D, fantasy, "
        "or surreal style. Portrait 4:5 composition.\n\n"
        "POST-DERIVED VISUAL SCENE:\n"
        f"{visual_description}\n\n"
        "Return only the described visual scene as an image."
    )
    negative_prompt = (
        "text, letters, captions, subtitles, watermark, logo, readable signage, "
        "infographic, poster, UI, chart, random courtroom, scales of justice, "
        "generic lawyer stock photo, generic law books, unrelated office scene, "
        "pharaonic, ancient Egypt, pyramids, sphinx, temples, hieroglyphs, sarcophagus, pharaoh, ancient statues, "
        "ancient Egyptian costume, papyrus, archaeological ruins, historical Egypt, stereotypical Egypt imagery, "
        "distorted hands, extra fingers, duplicate people, blurry faces, "
        "cartoon, illustration, 3D render, fantasy, surrealism, low quality"
    )

    def _generate_with_gemini() -> bytes:
        if not gemini_key:
            raise ImageGenerationError("GEMINI_API_KEY is missing for image fallback.")
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=gemini_key)
            model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
            response = client.models.generate_content(
                model=model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                ),
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

    endpoint = (
        CLOUDFLARE_IMAGE_ENDPOINT.format(account_id=account_id)
        if account_id and api_token else ""
    )

    width = 1024
    height = 1280
    try:
        num_steps = max(8, min(int(os.environ.get("CLOUDFLARE_IMAGE_STEPS", "20")), 20))
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
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "image/*",
    }

    cloudflare_error = None
    image_bytes = None
    if not endpoint:
        cloudflare_error = "Cloudflare credentials unavailable."
    else:
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=request_body,
                timeout=180,
            )
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

    if image_bytes is None:
        print(
            "Cloudflare image generation failed; trying Gemini with the SAME "
            f"post-derived prompt: {cloudflare_error}"
        )
        try:
            image_bytes = _generate_with_gemini()
            provider = "GEMINI_IMAGE_GENERATION"
        except Exception as gemini_error:
            raise ImageGenerationError(
                "Mandatory image generation failed. "
                f"Cloudflare={cloudflare_error}; Gemini={gemini_error}"
            ) from gemini_error
    else:
        provider = "DIRECT_CLOUDFLARE"

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image_bytes)

    if not output.exists() or output.stat().st_size == 0:
        raise ImageGenerationError("Generated image file is empty.")

    brand_published_image(str(output))
    print(f"Fresh post-derived editorial image generated: provider={provider} path={output}")
    print(f"Generated image size: {output.stat().st_size} bytes")
    return str(output)

