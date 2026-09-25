from __future__ import annotations

import base64
import os
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont, ImageOps

IMAGE_MODEL = os.getenv("KHYRAT_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-dev")
IMAGE_ENDPOINT = (
    "https://api.cloudflare.com/client/v4/accounts/"
    "{account_id}/ai/run/"
    "@cf/black-forest-labs/flux-2-dev"
)
MAX_PROMPT_LENGTH = 5000
IMAGE_STEPS = max(1, min(int(os.getenv("CLOUDFLARE_IMAGE_STEPS", "25")), 50))
DEFAULT_PAGE_NAME = "اسأل محمود - مستشار قانوني للشركات"

# Character reference assets are supplied directly to FLUX.2 [dev] as multi-reference
# image inputs when REFERENCE_SUBJECT mode is selected. The prompt also names the
# reference image slots explicitly so the model is instructed to preserve identity
# rather than inventing a generic professional man.
CHARACTER_REFERENCE_DIR = Path("assets/reference")
CHARACTER_REFERENCE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".avif"
}
CHARACTER_REFERENCE_PROFILE = (
    "The recurring male subject is an Egyptian professional man in his early-to-mid 30s, "
    "with a slim-to-average build, short dark black hair, a neatly trimmed short dark beard, "
    "medium-light warm skin tone, dark eyes, defined eyebrows, and a clean professional appearance. "
    "Keep facial identity and general proportions consistent across generated scenes, but do not copy "
    "any reference pose, camera angle, background, furniture, room, clothing, lighting setup, or framing."
)
CHARACTER_ANALYSIS_MODEL = os.getenv("KHYRAT_CHARACTER_ANALYSIS_MODEL", "gemini-3.1-flash-lite")
_CHARACTER_IDENTITY_PROFILE_CACHE: str | None = None
BRAND_MARGIN = 42
BRAND_HEIGHT = 96
BRAND_HORIZONTAL_PADDING = 30
BRAND_RADIUS = 28
BRAND_FONT_SIZE = 46
BRAND_MIN_FONT_SIZE = 26
BRAND_MAX_WIDTH_RATIO = 0.82
BRAND_BACKGROUND = (12, 12, 12, 215)
BRAND_TEXT = (255, 255, 255, 255)
FACEBOOK_BLUE = (24, 119, 242, 255)


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


def _build_character_identity_profile(reference_files: list[Path], gemini_api_key: str | None) -> str:
    """Analyze all available reference photos with a free-tier Gemini vision model.

    This is identity analysis only; it does not generate an image and does not store
    the resulting profile. The actual image generation remains on Cloudflare FLUX.
    """
    global _CHARACTER_IDENTITY_PROFILE_CACHE
    if _CHARACTER_IDENTITY_PROFILE_CACHE:
        return _CHARACTER_IDENTITY_PROFILE_CACHE
    if not gemini_api_key or not reference_files:
        return CHARACTER_REFERENCE_PROFILE

    prompt = """
Analyze the attached reference photos as multiple views of the SAME recurring male subject.
Create one concise English visual identity profile for an image-generation prompt.

Include only stable visual characteristics that help preserve resemblance:
- approximate age range
- face shape and proportions
- hair style/color
- beard/facial-hair pattern
- eyebrows and eyes
- skin tone
- distinctive but non-sensitive facial features
- general body/build proportions
- overall professional appearance

Do NOT identify or name the person.
Do NOT describe the locations, furniture, backgrounds, camera framing, poses, clothing,
lighting setups, or objects as identity traits.
Do NOT copy any single photograph.
Return one compact paragraph, no bullets, no markdown.
"""

    try:
        client = genai.Client(api_key=gemini_api_key)
        contents: list[Any] = [prompt]
        for path in reference_files:
            try:
                mime_type = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                    ".heic": "image/heic",
                    ".heif": "image/heif",
                    ".avif": "image/avif",
                }.get(path.suffix.lower())
                if not mime_type:
                    continue
                contents.append(
                    types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type)
                )
            except OSError as exc:
                print(f"Character reference read warning for {path.name}: {exc}")
        response = client.models.generate_content(
            model=CHARACTER_ANALYSIS_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(max_output_tokens=500),
        )
        profile = (getattr(response, "text", None) or "").strip()
        if profile:
            _CHARACTER_IDENTITY_PROFILE_CACHE = profile
            print(
                f"Character identity profile analyzed from {len(reference_files)} reference photo(s) "
                f"using {CHARACTER_ANALYSIS_MODEL}."
            )
            return profile
    except Exception as exc:
        print(f"Character identity analysis warning: {exc}; using fallback profile.")

    return CHARACTER_REFERENCE_PROFILE


def _build_prompt(topic: str, image_brief: str, character_profile: str | None = None, image_mode: str = "REFERENCE_SUBJECT") -> str:
    topic = topic.strip().replace("\r", " ").replace("\n", " ")
    brief = image_brief.strip().replace("\r", " ").replace("\n\n", "\n")
    if len(brief) > 900:
        brief = brief[:900].rsplit(" ", 1)[0].strip()
    mode = image_mode.strip().upper()
    if mode == "REFERENCE_SUBJECT":
        subject_block = f"""
REFERENCE SUBJECT MODE:
Use the supplied reference photos as the actual identity reference for the recurring male subject.
The person in the generated scene must visibly resemble the same person in the references.
Keep stable facial identity, hair, beard, skin tone, facial proportions, and general build consistent.
Create a completely new scene, pose, wardrobe, camera angle, environment, and composition.
Do not copy any reference photo's background, furniture, pose, framing, or lighting.
The recurring subject MUST be doing the exact legal action described in the visual brief.
REFERENCE INPUTS:
The uploaded reference photos are attached as input_image_0, input_image_1, input_image_2, and input_image_3 (whichever are present).
Use input_image_0 as the PRIMARY facial identity reference. Use input_image_1, input_image_2, and input_image_3 only as secondary consistency references. Preserve the same facial identity and recognizable features.
Do not invent a generic look. Do not substitute another man. The identity should be recognizable as the same person while the scene, pose, clothing, camera, and environment are new.
"""
    else:
        subject_block = """
CONTEXT-ONLY MODE:
Do NOT use the recurring lawyer as a subject.
Do NOT attempt to approximate his appearance.
Build the image entirely from the legal situation itself: the relevant people,
documents, objects, location, action, and emotional context.
"""
    prompt = f"""
Create one realistic cinematic editorial photograph.

{subject_block}

LEGAL STORY:
{topic}

CHARACTER IDENTITY PROFILE:
{character_profile or "Use the attached reference images as the identity source."}

VISUAL DIRECTOR BRIEF:
{brief}

Depict the exact legal situation described above, not a generic interpretation.
The image must communicate the same core fact pattern as the post.
Show the specific people, action, important document/object, setting, and practical tension.
Use realistic Egyptian context when appropriate.
Professional documentary/editorial photography.
Photorealistic people and materials. Preserve realistic anatomy and facial proportions.
Natural expressions and body language.
Medium shot or medium-wide shot; keep the face clearly visible and stable.
Do not make hands or fingers a focal element. If hands are visible, keep them naturally posed, anatomically correct, with exactly five fingers per hand and no overlapping or fused fingers.
No extra limbs, duplicated body parts, warped facial features, asymmetrical eyes, malformed teeth, distorted ears, or plastic-looking skin.
Strong focal subject.
Realistic cinematic lighting.
Natural depth of field.
Portrait-friendly 4:5 composition with the subject comfortably inside the frame and enough headroom. Avoid extreme close-ups, extreme wide angles, and aggressive perspective distortion.

The viewer should understand the legal situation from the image itself without reading the post.

ABSOLUTELY NO:
text, Arabic letters, English letters, readable writing,
headlines, captions, typography, logos, watermarks,
poster, infographic, presentation, quote card,
social-media template, collage, split screen, UI,
generic lawyer-at-desk scene, generic courthouse,
generic justice scales, random legal symbols,
abstract legal background, unrelated office scene.

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
        if candidate and Path(candidate).is_file():
            return Path(candidate)
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


def _measure_brand_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    try:
        bbox = draw.textbbox((0, 0), text, font=font, direction="rtl", language="ar")
    except (TypeError, ValueError):
        bbox = draw.textbbox((0, 0), text, font=font)
    return max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])


def _draw_brand_text(draw: ImageDraw.ImageDraw, position: tuple[int, int], text: str, font: ImageFont.ImageFont) -> None:
    try:
        draw.text(position, text, font=font, fill=BRAND_TEXT, anchor="rm", direction="rtl", language="ar")
    except (TypeError, ValueError):
        draw.text(position, text, font=font, fill=BRAND_TEXT, anchor="rm")


def _draw_facebook_badge(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int) -> None:
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=FACEBOOK_BLUE)
    font = _load_brand_font(int(radius * 1.65))
    try:
        draw.text((cx, cy + 2), "f", font=font, fill=(255, 255, 255, 255), anchor="mm")
    except Exception:
        draw.text((cx, cy), "f", font=font, fill=(255, 255, 255, 255), anchor="mm")


def _add_page_branding(image: Image.Image, page_name: str | None = None) -> Image.Image:
    name = (page_name or os.getenv("KHYRAT_PAGE_NAME", DEFAULT_PAGE_NAME)).strip() or DEFAULT_PAGE_NAME
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    max_text_width = int(base.width * BRAND_MAX_WIDTH_RATIO)
    font_size = BRAND_FONT_SIZE
    font = _load_brand_font(font_size)
    text_width, text_height = _measure_brand_text(draw, name, font)
    icon_radius = 26
    icon_gap = 18
    required_width = text_width + (BRAND_HORIZONTAL_PADDING * 2) + (icon_radius * 2) + icon_gap
    while required_width > int(base.width * 0.92) and font_size > BRAND_MIN_FONT_SIZE:
        font_size -= 2
        font = _load_brand_font(font_size)
        text_width, text_height = _measure_brand_text(draw, name, font)
        required_width = text_width + (BRAND_HORIZONTAL_PADDING * 2) + (icon_radius * 2) + icon_gap
    badge_width = min(base.width - (BRAND_MARGIN * 2), max(required_width, int(base.width * 0.46)))
    badge_height = max(BRAND_HEIGHT, text_height + 32)
    right = base.width - BRAND_MARGIN
    bottom = base.height - BRAND_MARGIN
    left = right - badge_width
    top = bottom - badge_height
    draw.rounded_rectangle((left, top, right, bottom), radius=BRAND_RADIUS, fill=BRAND_BACKGROUND)
    icon_center = (left + BRAND_HORIZONTAL_PADDING + icon_radius, top + (badge_height // 2))
    _draw_facebook_badge(draw, icon_center, icon_radius)
    _draw_brand_text(
        draw,
        (right - BRAND_HORIZONTAL_PADDING, top + (badge_height // 2)),
        name,
        font,
    )
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


def _prepare_reference_bytes(path: Path) -> bytes:
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=90, optimize=True)
            return buffer.getvalue()
    except Exception as exc:
        raise ImageGenerationError(f"Could not prepare reference image {path.name}: {exc}") from exc


def _cloudflare_generate(*, endpoint: str, headers: dict[str, str], prompt: str, reference_files: list[Path]) -> requests.Response:
    data = {
        "prompt": prompt,
        "steps": str(IMAGE_STEPS),
        "width": "1024",
        "height": "1280",
    }
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for index, ref in enumerate(reference_files[:4]):
        files.append((f"input_image_{index}", (ref.name, _prepare_reference_bytes(ref), "image/jpeg")))
    try:
        return requests.post(endpoint, headers=headers, data=data, files=files, timeout=240)
    except requests.RequestException as exc:
        raise ImageGenerationError(f"Cloudflare image request failed: {exc}") from exc


def create_legal_image(*, topic: str, image_brief: str, output_path: str, cloudflare_account_id: str | None = None, cloudflare_api_token: str | None = None, gemini_api_key: str | None = None, page_name: str | None = None, image_mode: str = "REFERENCE_SUBJECT") -> str:
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
    reference_dir = Path(os.getenv("KHYRAT_CHARACTER_REFERENCE_DIR", str(CHARACTER_REFERENCE_DIR)))
    reference_files = sorted(
        path for path in reference_dir.iterdir()
        if path.is_file() and path.suffix.lower() in CHARACTER_REFERENCE_EXTENSIONS
    )[:4] if reference_dir.is_dir() else []
    if reference_files:
        reference_names = ", ".join(path.name for path in reference_files)
        print(f"Character reference assets detected: {len(reference_files)} file(s) in {reference_dir}")
        print(f"Character reference files: {reference_names}")
    else:
        print(f"Character reference assets not found at {reference_dir}; continuing with identity profile only.")
    image_mode = (image_mode or "REFERENCE_SUBJECT").strip().upper()
    if image_mode != "REFERENCE_SUBJECT":
        raise ImageGenerationError(
            "Only REFERENCE_SUBJECT images are publishable; CONTEXT_ONLY is disabled by the publication contract."
        )
    if not reference_files:
        raise ImageGenerationError("REFERENCE_SUBJECT was requested but no reference images were found.")
    character_profile = _build_character_identity_profile(reference_files, gemini_api_key)
    prompt = _build_prompt(topic, image_brief, character_profile=character_profile, image_mode=image_mode)
    print(f"Cloudflare prompt length: {len(prompt)} characters | image_mode={image_mode}")
    endpoint = IMAGE_ENDPOINT.format(account_id=account_id)
    headers = {"Authorization": f"Bearer {api_token}", "Accept": "application/json"}
    response = _cloudflare_generate(
        endpoint=endpoint,
        headers=headers,
        prompt=prompt,
        reference_files=reference_files,
    )
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
