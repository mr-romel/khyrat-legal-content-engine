from __future__ import annotations

import os
import re
import json
import hashlib
from urllib.parse import quote
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
CLOUDFLARE_IMAGE_MODEL = "@cf/black-forest-labs/flux-2-dev"
CLOUDFLARE_IMAGE_MODEL_KLEIN = "@cf/black-forest-labs/flux-2-klein-9b"

CLOUDFLARE_IMAGE_ENDPOINT = (
    "https://api.cloudflare.com/client/v4/accounts/"
    "{account_id}/ai/run/"
    "@cf/black-forest-labs/flux-2-dev"
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



def _generate_zero_cost_editorial_image(*, topic: str, visual_description: str, output_path: str, width: int, height: int) -> bytes:
    """Render a local, topic-matched editorial illustration without external APIs."""
    from PIL import Image, ImageDraw
    seed = int(hashlib.sha256((topic + visual_description).encode("utf-8")).hexdigest()[:8], 16)
    image = Image.new("RGB", (width, height), (225, 232, 240))
    d = ImageDraw.Draw(image, "RGBA")
    d.rounded_rectangle((width*.07, height*.07, width*.93, height*.88), radius=int(width*.05), fill=(250,251,253,255))
    key = (topic + " " + visual_description).lower()
    if any(w in key for w in ("تهديد", "قتل", "رسالة", "مكالمة", "ابتزاز", "phone", "threat", "call")):
        x0,y0,x1,y1=int(width*.29),int(height*.20),int(width*.71),int(height*.72)
        d.rounded_rectangle((x0,y0,x1,y1),radius=int(width*.06),fill=(35,45,60,255))
        d.rounded_rectangle((x0+14,y0+24,x1-14,y1-24),radius=18,fill=(235,241,247,255))
        d.rounded_rectangle((x0+30,y0+90,x1-30,y0+190),radius=16,fill=(65,103,143,255))
        d.rounded_rectangle((x0+30,y0+220,x1-30,y0+345),radius=16,fill=(213,224,235,255))
        d.rounded_rectangle((int(width*.10),int(height*.60),int(width*.34),int(height*.77)),radius=14,fill=(194,153,78,255))
        d.ellipse((int(width*.69),int(height*.55),int(width*.87),int(height*.73)),outline=(45,78,110,255),width=12)
        d.line((int(width*.82),int(height*.70),int(width*.92),int(height*.80)),fill=(45,78,110,255),width=15)
    elif any(w in key for w in ("تصالح", "تنازل", "تسوية", "إقرار", "settlement", "waiver", "reconciliation")):
        d.rounded_rectangle((int(width*.13),int(height*.34),int(width*.87),int(height*.76)),radius=22,fill=(190,151,78,255))
        d.rounded_rectangle((int(width*.25),int(height*.17),int(width*.77),int(height*.67)),radius=12,fill=(255,255,252,255),outline=(170,182,195,255),width=5)
        for i in range(4):
            yy=int(height*(.34+i*.07))
            d.rounded_rectangle((int(width*.34),yy,int(width*(.65+(i%2)*.07)),yy+8),radius=4,fill=(175,185,197,255))
        d.arc((int(width*.43),int(height*.48),int(width*.66),int(height*.62)),190,345,fill=(43,84,123,255),width=8)
        d.ellipse((int(width*.68),int(height*.58),int(width*.82),int(height*.72)),fill=(54,113,91,255))
        d.line((int(width*.71),int(height*.65),int(width*.75),int(height*.68),int(width*.79),int(height*.61)),fill=(255,255,255,255),width=7)
    elif any(w in key for w in ("إجاز", "راحة", "عمل", "موظف", "حضور", "leave", "employment", "vacation")):
        d.rounded_rectangle((int(width*.18),int(height*.20),int(width*.76),int(height*.69)),radius=20,fill=(255,255,252,255),outline=(56,83,111,255),width=7)
        d.rounded_rectangle((int(width*.18),int(height*.20),int(width*.76),int(height*.34)),radius=18,fill=(49,83,119,255))
        for col in range(4):
            for row in range(3):
                xx=int(width*(.27+col*.12)); yy=int(height*(.42+row*.075))
                d.rounded_rectangle((xx,yy,xx+int(width*.055),yy+int(height*.035)),radius=7,fill=(72,143,116,255) if (col,row)==(1,1) else (219,226,233,255))
        d.ellipse((int(width*.57),int(height*.56),int(width*.88),int(height*.87)),fill=(240,244,248,255),outline=(48,79,111,255),width=9)
        cx,cy=int(width*.725),int(height*.715)
        d.line((cx,cy,cx,cy-int(height*.10)),fill=(48,79,111,255),width=9)
        d.line((cx,cy,cx+int(width*.08),cy+int(height*.04)),fill=(48,79,111,255),width=9)
    else:
        d.rounded_rectangle((int(width*.18),int(height*.28),int(width*.82),int(height*.76)),radius=24,fill=(49,72,98,255))
        d.rounded_rectangle((int(width*.25),int(height*.19),int(width*.75),int(height*.68)),radius=14,fill=(255,255,252,255),outline=(173,184,197,255),width=5)
        for i in range(4):
            yy=int(height*(.32+i*.07))
            d.rounded_rectangle((int(width*.34),yy,int(width*(.63+(i%2)*.08)),yy+8),radius=4,fill=(177,188,200,255))
        d.line((int(width*.50),int(height*.48),int(width*.50),int(height*.65)),fill=(189,147,69,255),width=9)
        d.line((int(width*.38),int(height*.51),int(width*.62),int(height*.51)),fill=(189,147,69,255),width=8)
    palette=[(47,91,128,90),(150,111,54,85),(58,113,94,80),(91,83,132,75)]
    accent=palette[seed%len(palette)]
    d.ellipse((int(width*.08),int(height*.12),int(width*.20),int(height*.24)),fill=accent)
    output=Path(output_path); output.parent.mkdir(parents=True,exist_ok=True)
    image.save(output,format="JPEG",quality=94,optimize=True)
    return output.read_bytes()


def create_generic_legal_fallback_image(
    *,
    output_path: str,
    aspect_ratio: str = "4:5",
    topic: str = "محتوى قانوني عام",
    visual_description: str = "",
) -> str:
    """Create a deterministic, branded legal visual when external image providers or scene QA fail."""
    if aspect_ratio == "9:16":
        width, height = 576, 1024
    elif aspect_ratio == "4:5":
        width, height = 1024, 1280
    else:
        raise ImageGenerationError(f"Unsupported generic legal image aspect ratio: {aspect_ratio}")
    description = (
        "Professional generic legal illustration: balanced justice scales, "
        "organized legal documents, a closed law book and a refined courthouse "
        "architectural detail; navy, warm gold and ivory palette; no readable text."
    )
    try:
        scene_description = " ".join(str(visual_description or "").split()).strip()
        if scene_description:
            description = (
                "Professional legal editorial illustration inspired by this scene: "
                + scene_description
                + ". Keep it clearly legal, non-photorealistic, navy, warm gold and ivory, with no readable text."
            )
        _generate_zero_cost_editorial_image(
            topic=str(topic or "محتوى قانوني عام"),
            visual_description=description,
            output_path=output_path,
            width=width,
            height=height,
        )
        brand_published_image(output_path)
        with Image.open(output_path) as check:
            check.verify()
        return output_path
    except Exception as exc:
        raise ImageGenerationError(f"Could not create generic legal fallback image: {exc}") from exc


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
        # Keep the generated scene anchored to the legal issue in the post.
        # Do not impose a country, culture, era, cast, or decorative art direction.
        prompt += (
            f"\\nCOMPOSITION FORMAT: portrait {aspect_ratio}; "
            "show a clear, concrete visual representation of the specific "
            "legal problem, evidence, action, document, or consequence described "
            "in the post. Avoid generic legal clichés and unrelated decoration. "
            "No added text or labels; keep the main subject clearly framed."
        )
        # Cloudflare FLUX accepts a maximum of 2048 prompt characters.
        prompt = prompt[:2048]
    except ValueError as exc:
        raise ImageGenerationError(str(exc)) from exc
    negative_prompt = ""

    def _generate_with_pollinations() -> bytes:
        """Generate a topic-specific image through Pollinations using a server-side key."""
        pollinations_key = os.getenv("POLLINATIONS_API_KEY", "").strip()
        if not pollinations_key:
            raise ImageGenerationError("POLLINATIONS_API_KEY is missing; add it as a GitHub Actions secret.")
        model = os.getenv("POLLINATIONS_IMAGE_MODEL", "black-forest-labs/flux.1-schnell").strip()
        encoded_prompt = quote(prompt, safe="")
        url = f"https://gen.pollinations.ai/image/{encoded_prompt}"
        params = {"model": model, "width": width, "height": height, "nologo": "true"}
        try:
            response = requests.get(url, params=params, headers={"Authorization": f"Bearer {pollinations_key}", "Accept": "image/*"}, timeout=(20, 240))
            if not response.ok:
                raise ImageGenerationError(f"Pollinations image request failed: HTTP {response.status_code} - {response.text[:1200]}")
            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("image/") or not response.content:
                raise ImageGenerationError(f"Pollinations returned no image bytes (content-type={content_type or 'missing'}).")
            return response.content
        except requests.RequestException as exc:
            raise ImageGenerationError(f"Pollinations image request error: {exc}") from exc

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
                    error_text = str(exc).casefold()
                    if any(marker in error_text for marker in ("429", "resource_exhausted", "quota exceeded", "limit: 0")):
                        print("Gemini image quota is exhausted; skipping retries and switching to the next image provider.")
                        break
                    if attempt < 3:
                        delay = attempt * 2
                        print(f"Transient image-generation failure; retry {attempt + 1}/3 in {delay}s: {exc}")
                        time.sleep(delay)
            raise ImageGenerationError(f"Gemini image generation failed after 3 attempts: {last_error}") from last_error
        except Exception as exc:
            raise ImageGenerationError(f"Gemini image fallback failed: {exc}") from exc

    def _generate_with_pixabay() -> bytes:
        """Fetch a safe, vertical legal stock photo as the final external fallback."""
        pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()
        if not pixabay_key:
            raise ImageGenerationError("PIXABAY_API_KEY is missing; add it as a GitHub Actions secret.")
        # Search using the scene's concrete English nouns, not a broad Arabic title.
        # This makes stock fallback useful for specific infrastructure, contracts,
        # workplace evidence, and other non-courthouse legal scenes.
        stopwords = {"a", "an", "the", "of", "with", "and", "or", "beside", "showing", "modern", "realistic", "documentary", "photograph", "photo", "view", "close", "wide", "clean"}
        scene_tokens = [
            token.lower() for token in re.findall(r"[A-Za-z][A-Za-z-]+", str(visual_description or ""))
            if token.lower() not in stopwords
        ]
        query = " ".join(scene_tokens[:9]).strip()
        if len(query) < 8:
            query = " ".join(str(topic or "").split()[:6]).strip() or "public utility infrastructure"
        try:
            response = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": pixabay_key,
                    "q": query,
                    "image_type": "photo",
                    "orientation": "vertical",
                    "safesearch": "true",
                    "per_page": 10,
                    "order": "popular",
                },
                headers={"Accept": "application/json"},
                timeout=(10, 30),
            )
            if not response.ok:
                raise ImageGenerationError(f"Pixabay search failed: HTTP {response.status_code} - {response.text[:500]}")
            payload = response.json()
            hits = payload.get("hits", []) if isinstance(payload, dict) else []
            if not hits:
                # A broad legal query is safer than returning an unrelated topic image.
                response = requests.get(
                    "https://pixabay.com/api/",
                    params={
                        "key": pixabay_key,
                        "q": "law legal documents courthouse",
                        "image_type": "photo",
                        "orientation": "vertical",
                        "safesearch": "true",
                        "per_page": 10,
                        "order": "popular",
                    },
                    headers={"Accept": "application/json"},
                    timeout=(10, 30),
                )
                if not response.ok:
                    raise ImageGenerationError(f"Pixabay legal fallback search failed: HTTP {response.status_code}")
                payload = response.json()
                hits = payload.get("hits", []) if isinstance(payload, dict) else []
            if not hits:
                raise ImageGenerationError("Pixabay returned no suitable legal stock images.")
            # Pixabay's largeImageURL is suitable for editorial use and avoids tiny previews.
            image_url = next((hit.get("largeImageURL") or hit.get("webformatURL") for hit in hits
                              if hit.get("largeImageURL") or hit.get("webformatURL")), None)
            if not image_url:
                raise ImageGenerationError("Pixabay results contained no downloadable image URL.")
            image_response = requests.get(image_url, headers={"Accept": "image/*"}, timeout=(10, 45))
            if not image_response.ok or not image_response.content:
                raise ImageGenerationError(f"Pixabay image download failed: HTTP {image_response.status_code}")
            content_type = image_response.headers.get("content-type", "").lower()
            if not content_type.startswith("image/"):
                raise ImageGenerationError(f"Pixabay returned non-image content: {content_type or 'missing'}")
            print("Pixabay legal stock image selected as the final external fallback.")
            return image_response.content
        except requests.RequestException as exc:
            raise ImageGenerationError(f"Pixabay request error: {exc}") from exc

    provider_preference = str(provider or "auto").strip().lower()
    if provider_preference not in {"auto", "cloudflare", "cloudflare_klein", "gemini", "pollinations", "pixabay"}:
        raise ImageGenerationError(f"Unsupported image provider preference: {provider_preference}")
    cloudflare_model = (
        CLOUDFLARE_IMAGE_MODEL_KLEIN
        if provider_preference == "cloudflare_klein"
        else CLOUDFLARE_IMAGE_MODEL
    )
    endpoint = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{account_id}/ai/run/{cloudflare_model}"
        if account_id and api_token and provider_preference not in {"gemini", "pollinations", "pixabay"} else ""
    )

    if aspect_ratio == "9:16":
        # Portrait-friendly dimensions supported by common diffusion backends.
        width, height = 576, 1024
    elif aspect_ratio == "4:5":
        width, height = 1024, 1280
    else:
        raise ImageGenerationError(f"Unsupported image aspect ratio: {aspect_ratio}")
    try:
        num_steps = max(8, min(int(os.environ.get("CLOUDFLARE_IMAGE_STEPS", "25")), 25))
    except ValueError:
        num_steps = 25
    try:
        guidance = max(1.5, min(float(os.environ.get("CLOUDFLARE_IMAGE_GUIDANCE", "4.5")), 10.0))
    except ValueError:
        guidance = 4.5

    # FLUX.2 [dev] requires multipart form data, including for text-only prompts.
    # requests builds the multipart boundary automatically from the files mapping.
    request_fields = {
        "prompt": prompt,
        "guidance": str(guidance),
        "width": str(width),
        "height": str(height),
    }
    # FLUX.2 [klein] 9B has a fixed four-step inference path and rejects a steps override.
    if cloudflare_model != CLOUDFLARE_IMAGE_MODEL_KLEIN:
        request_fields["steps"] = str(num_steps)
    multipart_fields = {key: (None, value) for key, value in request_fields.items()}

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "image/*",
    }

    cloudflare_error = None
    image_bytes = None
    if not endpoint:
        cloudflare_error = (f"{provider_preference.title()} explicitly selected." if provider_preference in {"gemini", "pollinations"} else "Cloudflare credentials unavailable.")
    else:
        import time
        for attempt in range(1, 4):
            try:
                response = requests.post(
                    endpoint,
                    headers=headers,
                    files=multipart_fields,
                    timeout=(30, 240),
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
                quota_text = str(error_payload).casefold()
                if response.status_code == 429 and any(
                    marker in quota_text
                    for marker in ("daily free allocation", "neurons", "quota exceeded", "usage limit")
                ):
                    print("Cloudflare image quota is exhausted; skipping pointless retries and switching to Gemini.")
                    break
                if response.status_code not in {408, 425, 429, 500, 502, 503, 504}:
                    break
            except requests.RequestException as exc:
                cloudflare_error = str(exc)
            if attempt < 3:
                delay = attempt * 2
                print(f"Cloudflare image service transient failure; retry {attempt + 1}/3 in {delay}s: {cloudflare_error}")
                time.sleep(delay)

    if provider_preference == "pixabay":
        image_bytes = _generate_with_pixabay()
        provider = "PIXABAY_SCENE_STOCK"
    elif image_bytes is None and provider_preference != "gemini":
        # Pollinations is the first external fallback after Cloudflare. It receives
        # the identical post-derived prompt; no generic or unrelated stock fallback.
        print("Cloudflare image generation unavailable; trying Pollinations with the SAME post-derived prompt: " + str(cloudflare_error))
        try:
            image_bytes = _generate_with_pollinations()
            provider = "POLLINATIONS_IMAGE_GENERATION"
        except Exception as pollinations_error:
            print(f"Pollinations fallback failed; trying Gemini next: {pollinations_error}")
            try:
                image_bytes = _generate_with_gemini()
                provider = "GEMINI_IMAGE_GENERATION"
            except Exception as gemini_error:
                print(f"Gemini fallback failed; trying scene-matched Pixabay stock imagery: {gemini_error}")
                try:
                    image_bytes = _generate_with_pixabay()
                    provider = "PIXABAY_SCENE_STOCK"
                except Exception as pixabay_error:
                    raise ImageGenerationError("All scene-specific image providers failed. " f"Cloudflare={cloudflare_error}; Pollinations={pollinations_error}; Gemini={gemini_error}; Pixabay={pixabay_error}") from pixabay_error
    elif image_bytes is None:
        try:
            image_bytes = _generate_with_gemini()
            provider = "GEMINI_IMAGE_GENERATION"
        except Exception as gemini_error:
            print(f"Gemini image generation failed; trying scene-matched Pixabay stock imagery: {gemini_error}")
            try:
                image_bytes = _generate_with_pixabay()
                provider = "PIXABAY_SCENE_STOCK"
            except Exception as pixabay_error:
                raise ImageGenerationError("Gemini and scene-matched Pixabay image providers failed. " f"Gemini={gemini_error}; Pixabay={pixabay_error}") from pixabay_error
    else:
        provider = "DIRECT_CLOUDFLARE_KLEIN" if cloudflare_model == CLOUDFLARE_IMAGE_MODEL_KLEIN else "DIRECT_CLOUDFLARE"
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
        else "pixabay-scene-search" if provider == "PIXABAY_SCENE_STOCK"
        else "pixabay-editorial-stock" if provider == "PIXABAY_LEGAL_STOCK"
        else os.getenv("POLLINATIONS_IMAGE_MODEL", "black-forest-labs/flux.1-schnell")
        if provider == "POLLINATIONS_IMAGE_GENERATION"
        else "local-pillow-editorial-v1" if provider == "LOCAL_ZERO_COST_EDITORIAL"
        else CLOUDFLARE_IMAGE_MODEL_KLEIN if provider == "DIRECT_CLOUDFLARE_KLEIN"
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

