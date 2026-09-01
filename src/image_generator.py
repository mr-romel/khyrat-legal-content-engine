from __future__ import annotations

import base64
import os
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
IMAGE_ENDPOINT = (
    "https://api.cloudflare.com/client/v4/accounts/"
    "{account_id}/ai/run/"
    "@cf/black-forest-labs/flux-1-schnell"
)
MAX_PROMPT_LENGTH = 1800
# Keep image generation deliberately inexpensive. FLUX Schnell consumes more
# Workers AI neurons as sampling steps increase; 4 is sufficient for this
# editorial use and halves the previous 8-step request cost.
IMAGE_STEPS = max(1, min(int(os.getenv("CLOUDFLARE_IMAGE_STEPS", "4")), 4))
DEFAULT_PAGE_NAME = "اسأل محمود"
BRAND_MARGIN = 42
BRAND_HEIGHT = 88
BRAND_HORIZONTAL_PADDING = 36
BRAND_RADIUS = 28
BRAND_FONT_SIZE = 52
BRAND_MIN_FONT_SIZE = 30
BRAND_MAX_WIDTH_RATIO = 0.72
BRAND_BACKGROUND = (12, 12, 12, 208)
BRAND_TEXT = (255, 255, 255, 255)

class ImageGenerationError(RuntimeError):
    """Raised when Cloudflare image generation or finalization fails."""

def _extract_image_bytes(response: requests.Response) -> bytes:
    content_type = response.headers.get("content-type", "").lower()
    if content_type.startswith("image/"):
        if not response.content:
            raise ImageGenerationError("Cloudflare returned an empty image response.")
        return response.content
    try:
        payload: dict[str, Any] = response.json()
    except ValueError as exc:
        raise ImageGenerationError("Cloudflare returned neither an image nor valid JSON.") from exc
    if not payload.get("success", False):
        raise ImageGenerationError(f"Cloudflare AI request failed: {payload.get('errors') or payload}")
    result = payload.get("result")
    image_base64: str | None = None
    if isinstance(result, dict):
        image_base64 = result.get("image")
    elif isinstance(result, str):
        image_base64 = result
    if not image_base64:
        raise ImageGenerationError("Cloudflare returned no image data.")
    try:
        return base64.b64decode(image_base64, validate=True)
    except Exception as exc:
        raise ImageGenerationError("Cloudflare returned invalid Base64 image data.") from exc

def _build_prompt(topic: str, image_brief: str) -> str:
    topic = topic.strip().replace("\r", " ").replace("\n", " ")
    brief = image_brief.strip().replace("\r", " ").replace("\n\n", "\n")
    if len(brief) > 900:
        brief = brief[:900].rsplit(" ", 1)[0].strip()
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
        prompt = prompt[:MAX_PROMPT_LENGTH].rsplit(" ", 1)[0].strip()
    return prompt

def _find_brand_font() -> Path | None:
    candidates = [
        os.getenv("KHYRAT_BRAND_FONT", "").strip(),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            return path
    return None

def _load_brand_font(size: int) -> ImageFont.ImageFont:
    font_path = _find_brand_font()
    if font_path is None:
        print("Branding warning: no system Arabic-capable font was found; Pillow default font will be used.")
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception as exc:
        print(f"Branding warning: could not load font '{font_path}': {exc}. Using Pillow default font.")
        return ImageFont.load_default()

def _measure_brand_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int, tuple[int, int, int, int]]:
    try:
        bbox = draw.textbbox((0, 0), text, font=font, direction="rtl", language="ar")
        return max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1]), bbox
    except (TypeError, ValueError):
        bbox = draw.textbbox((0, 0), text, font=font)
        return max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1]), bbox

def _draw_brand_text(draw: ImageDraw.ImageDraw, position: tuple[int, int], text: str, font: ImageFont.ImageFont) -> None:
    try:
        draw.text(position, text, font=font, fill=BRAND_TEXT, anchor="rm", direction="rtl", language="ar")
    except (TypeError, ValueError):
        draw.text(position, text, font=font, fill=BRAND_TEXT, anchor="rm")

def _add_page_branding(image: Image.Image, page_name: str | None = None) -> Image.Image:
    name = (page_name or os.getenv("KHYRAT_PAGE_NAME", DEFAULT_PAGE_NAME)).strip() or DEFAULT_PAGE_NAME
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    max_text_width = int(base.width * BRAND_MAX_WIDTH_RATIO)
    font_size = BRAND_FONT_SIZE
    font = _load_brand_font(font_size)
    text_width, text_height, _ = _measure_brand_text(draw, name, font)
    while text_width > max_text_width and font_size > BRAND_MIN_FONT_SIZE:
        font_size -= 2
        font = _load_brand_font(font_size)
        text_width, text_height, _ = _measure_brand_text(draw, name, font)
    badge_width = min(base.width - (BRAND_MARGIN * 2), text_width + (BRAND_HORIZONTAL_PADDING * 2))
    badge_height = max(BRAND_HEIGHT, text_height + 32)
    right = base.width - BRAND_MARGIN
    bottom = base.height - BRAND_MARGIN
    left = right - badge_width
    top = bottom - badge_height
    draw.rounded_rectangle((left, top, right, bottom), radius=BRAND_RADIUS, fill=BRAND_BACKGROUND)
    accent_width = 6
    accent_margin = 18
    draw.rounded_rectangle((left + accent_margin, top + 20, left + accent_margin + accent_width, bottom - 20), radius=accent_width // 2, fill=(214, 174, 92, 255))
    _draw_brand_text(draw, (right - BRAND_HORIZONTAL_PADDING, top + (badge_height // 2)), name, font)
    return Image.alpha_composite(base, overlay).convert("RGB")

def _convert_to_4x5(image_bytes: bytes, output_path: Path, page_name: str | None = None) -> None:
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise ImageGenerationError(f"Could not decode generated image: {exc}") from exc
    final_image = ImageOps.fit(image, (1024, 1280), method=Image.Resampling.LANCZOS, centering=(0.5, 0.43))
    final_image = _add_page_branding(final_image, page_name=page_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_image.save(output_path, format="JPEG", quality=94, optimize=True)

def create_legal_image(*, topic: str, image_brief: str, output_path: str, cloudflare_account_id: str | None = None, cloudflare_api_token: str | None = None, page_name: str | None = None) -> str:
    account_id = (cloudflare_account_id or "").strip()
    api_token = (cloudflare_api_token or "").strip()
    if not account_id:
        raise ImageGenerationError("CLOUDFLARE_ACCOUNT_ID is missing.")
    if not api_token:
        raise ImageGenerationError("CLOUDFLARE_API_TOKEN is missing.")
    if not topic.strip():
        raise ImageGenerationError("Topic is empty.")
    if not image_brief.strip():
        raise ImageGenerationError("Image brief is empty.")
    prompt = _build_prompt(topic, image_brief)
    print(f"Cloudflare prompt length: {len(prompt)} characters")
    endpoint = IMAGE_ENDPOINT.format(account_id=account_id)
    request_body = {"prompt": prompt, "steps": IMAGE_STEPS}
    if "seed" in request_body:
        raise ImageGenerationError("Internal safety check failed: unsupported 'seed' field.")
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json", "Accept": "application/json"}
    try:
        response = requests.post(endpoint, headers=headers, json=request_body, timeout=180)
    except requests.RequestException as exc:
        raise ImageGenerationError(f"Cloudflare image request failed: {exc}") from exc
    if not response.ok:
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = response.text
        raise ImageGenerationError(f"Cloudflare image API failed: HTTP {response.status_code} - {error_payload}")
    image_bytes = _extract_image_bytes(response)
    if not image_bytes:
        raise ImageGenerationError("Cloudflare returned empty image bytes.")
    output = Path(output_path)
    _convert_to_4x5(image_bytes, output, page_name=page_name)
    if not output.exists() or output.stat().st_size == 0:
        raise ImageGenerationError("Final image file is empty.")
    print(f"Cloudflare FLUX image generated successfully: {output}")
    print(f"Cloudflare FLUX steps: {IMAGE_STEPS}")
    print(f"Final image size: {output.stat().st_size} bytes")
    print(f"Page branding applied successfully: {page_name or os.getenv('KHYRAT_PAGE_NAME', DEFAULT_PAGE_NAME)}")
    return str(output)
