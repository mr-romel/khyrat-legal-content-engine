from __future__ import annotations

import os
import re
import json
import hashlib
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import arabic_reshaper
from bidi.algorithm import get_display

from brand_identity import (
    BRAND_ACCENT, BRAND_OVERLAY_TEXT, BRAND_OVERLAY_SUBTEXT,
    BRAND_PRIMARY, BRAND_WHITE, FACEBOOK_BADGE_BLUE, BLOGGER_BADGE_GREEN,
    build_editorial_image_prompt,
)


# FLUX follows detailed editorial prompts more reliably than SDXL Lightning.
CLOUDFLARE_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"

CLOUDFLARE_IMAGE_ENDPOINT = (
    "https://api.cloudflare.com/client/v4/accounts/"
    "{account_id}/ai/run/"
    "@cf/black-forest-labs/flux-1-schnell"
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
    """Apply the unified Ask Mahmoud professional identity to every published image."""
    path = Path(image_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ImageGenerationError("Cannot brand a missing image.")

    try:
        image = Image.open(path).convert("RGB")
        width, height = image.size
        draw = ImageDraw.Draw(image, "RGBA")
        strip_h = max(108, int(height * 0.13))
        y0 = height - strip_h
        navy = (*BRAND_PRIMARY, 232)
        gold = (*BRAND_ACCENT, 255)
        white = (*BRAND_WHITE, 255)
        draw.rectangle((0, y0, width, height), fill=navy)
        draw.rectangle((0, y0, width, y0 + max(4, int(height * 0.006))), fill=gold)

        font_candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        font_path = next((p for p in font_candidates if Path(p).exists()), None)
        main_size = max(22, int(width * 0.032))
        sub_size = max(13, int(width * 0.016))
        main_font = ImageFont.truetype(font_path, main_size) if font_path else ImageFont.load_default()
        sub_font = ImageFont.truetype(font_path, sub_size) if font_path else ImageFont.load_default()
        right = width - max(22, int(width * 0.035))
        # The only permitted wording on the image is this exact approved line.
        # No platform names, extra descriptors, captions, or generated text.
        _draw_arabic_text(draw, (right, y0 + int(strip_h * 0.52)), BRAND_OVERLAY_TEXT,
                          font=main_font, fill=white, anchor="rm")

        # Platform symbols only: no "Facebook" or "Blogger" text labels.
        badge_d = max(30, min(int(strip_h * 0.48), int(width * 0.078)))
        badge_gap = max(10, int(badge_d * 0.24))
        badge_y = y0 + (strip_h - badge_d) // 2
        badge_x = max(18, int(width * 0.04))

        # Facebook: blue roundel with the recognizable white lowercase f.
        fx = badge_x
        draw.ellipse((fx, badge_y, fx + badge_d, badge_y + badge_d),
                     fill=(*FACEBOOK_BADGE_BLUE, 255))
        f_size = max(20, int(badge_d * 0.86))
        f_font = ImageFont.truetype(font_path, f_size) if font_path else ImageFont.load_default()
        fb = draw.textbbox((0, 0), "f", font=f_font)
        fw, fh = fb[2] - fb[0], fb[3] - fb[1]
        draw.text((fx + (badge_d-fw)/2-fb[0], badge_y + (badge_d-fh)/2-fb[1] - int(badge_d*0.06)),
                  "f", font=f_font, fill=white)

        # Blogger: green roundel with a white Blogger-style geometric B mark.
        bx = badge_x + badge_d + badge_gap
        draw.ellipse((bx, badge_y, bx + badge_d, badge_y + badge_d),
                     fill=(*BLOGGER_BADGE_GREEN, 255))
        mark_w = int(badge_d * 0.52)
        mark_h = int(badge_d * 0.62)
        mx = bx + (badge_d - mark_w) // 2
        my = badge_y + (badge_d - mark_h) // 2
        draw.rounded_rectangle((mx, my, mx + mark_w, my + mark_h),
                               radius=max(3, badge_d // 10), outline=white,
                               width=max(2, badge_d // 10))
        draw.line((mx + mark_w//2, my + 2, mx + mark_w//2, my + mark_h - 2),
                  fill=white, width=max(2, badge_d // 10))

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
    aspect_ratio: str = "4:5",
    provider: str = "auto",
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

    # Use the post-derived visual description directly as requested. Avoid extra
    # negative prompts and arbitrary subject restrictions that can block generation.
    try:
        prompt = build_editorial_image_prompt(
            topic=topic,
            post_context=post_context,
            visual_description=visual_description,
        )
        prompt += (
            f"\\nCOMPOSITION FORMAT: portrait {aspect_ratio}; "
            "frame the key action and evidence safely inside the central area, "
            "with enough headroom and no critical details near the crop edges. "
            "Contemporary Egyptian legal-office editorial photography, "
            "modern people and present-day office interiors. Strictly exclude "
            "pharaonic or ancient Egyptian motifs, pyramids, temples, statues, "
            "hieroglyphs, museums, historical costumes, fantasy, and antique scenes."
        )
        # Cloudflare FLUX accepts a maximum of 2048 prompt characters.
        prompt = prompt[:2048]
    except ValueError as exc:
        raise ImageGenerationError(str(exc)) from exc
    negative_prompt = ""

    def _generate_with_gemini() -> bytes:
        if not gemini_key:
            raise ImageGenerationError("GEMINI_API_KEY is missing for image fallback.")
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=gemini_key)
            model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
            import time
            last_error = None
            for attempt in range(1, 4):
                try:
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
                    last_error = exc
                    if attempt < 3:
                        delay = attempt * 2
                        print(f"Transient image-generation failure; retry {attempt + 1}/3 in {delay}s: {exc}")
                        time.sleep(delay)
            raise ImageGenerationError(f"Gemini image generation failed after 3 attempts: {last_error}") from last_error
        except Exception as exc:
            raise ImageGenerationError(f"Gemini image fallback failed: {exc}") from exc

    provider_preference = str(provider or "auto").strip().lower()
    if provider_preference not in {"auto", "cloudflare", "gemini"}:
        raise ImageGenerationError(f"Unsupported image provider preference: {provider_preference}")
    endpoint = (
        CLOUDFLARE_IMAGE_ENDPOINT.format(account_id=account_id)
        if account_id and api_token and provider_preference != "gemini" else ""
    )

    if aspect_ratio == "9:16":
        # Portrait-friendly dimensions supported by common diffusion backends.
        width, height = 576, 1024
    elif aspect_ratio == "4:5":
        width, height = 1024, 1280
    else:
        raise ImageGenerationError(f"Unsupported image aspect ratio: {aspect_ratio}")
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
        # FLUX.1 schnell accepts only prompt and steps (4–8).
        "steps": max(4, min(num_steps, 8)),
    }

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "image/*",
    }

    cloudflare_error = None
    image_bytes = None
    if not endpoint:
        cloudflare_error = ("Gemini explicitly selected after visual QA rejection." if provider_preference == "gemini" else "Cloudflare credentials unavailable.")
    else:
        import time
        for attempt in range(1, 4):
            try:
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=request_body,
                    timeout=(20, 180),
                )
                if response.ok:
                    try:
                        image_bytes = _extract_image_bytes(response)
                    except ImageGenerationError as exc:
                        cloudflare_error = str(exc)
                    if image_bytes is not None:
                        break
                    # Invalid/non-image responses fall through to the Gemini
                    # provider below rather than aborting image generation.
                    break
                try:
                    error_payload = response.json()
                except ValueError:
                    error_payload = response.text
                cloudflare_error = f"HTTP {response.status_code} - {error_payload}"
                if response.status_code not in {408, 425, 429, 500, 502, 503, 504}:
                    break
            except requests.RequestException as exc:
                cloudflare_error = str(exc)
            if attempt < 3:
                delay = attempt * 2
                print(f"Cloudflare image service transient failure; retry {attempt + 1}/3 in {delay}s: {cloudflare_error}")
                time.sleep(delay)

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

    # FLUX returns a square canvas; crop to the requested Reel portrait ratio.
    try:
        with Image.open(output) as generated:
            portrait = ImageOps.fit(
                generated.convert("RGB"),
                (width, height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.45),
            )
            portrait.save(output, format="JPEG", quality=94, optimize=True)
    except Exception as exc:
        raise ImageGenerationError(f"Could not normalize generated image to portrait format: {exc}") from exc

    brand_published_image(str(output))
    image_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    provider_model = (
        os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
        if provider == "GEMINI_IMAGE_GENERATION"
        else CLOUDFLARE_IMAGE_MODEL
    )
    provenance = {
        "topic": str(topic or ""),
        "provider": provider,
        "model": provider_model,
        "prompt": prompt,
        "prompt_sha256": prompt_sha256,
        "image_sha256": image_sha256,
        "image_path": str(output),
        "visual_description": visual_description,
        "aspect_ratio": aspect_ratio,
        "width": width,
        "height": height,
        "qa_decision": "PENDING",
    }
    provenance_path = output.with_suffix(output.suffix + ".provenance.json")
    provenance_path.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Fresh post-derived editorial image generated: provider={provider} "
        f"model={provider_model} image_sha256={image_sha256} path={output}"
    )
    print(f"Image provenance saved: {provenance_path}")
    print(f"Generated image size: {output.stat().st_size} bytes")
    return str(output)

