from __future__ import annotations

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

DEFAULT_PAGE_NAME = "اسأل محمود"
MARGIN = 42
HEIGHT = 88
PADDING = 36
RADIUS = 28
FONT_SIZE = 52
MIN_FONT_SIZE = 30
MAX_WIDTH_RATIO = 0.72
BACKGROUND = (12, 12, 12, 208)
TEXT = (255, 255, 255, 255)


def _font_path() -> Path | None:
    candidates = [
        os.getenv("KHYRAT_BRAND_FONT", "").strip(),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Arial.ttf",
    ]
    for value in candidates:
        if value and Path(value).is_file():
            return Path(value)
    return None


def _load_font(size: int) -> ImageFont.ImageFont:
    path = _font_path()
    if path is None:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        return ImageFont.load_default()


def _measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    try:
        box = draw.textbbox((0, 0), text, font=font, direction="rtl", language="ar")
    except (TypeError, ValueError):
        box = draw.textbbox((0, 0), text, font=font)
    return max(1, box[2] - box[0]), max(1, box[3] - box[1])


def _draw(draw: ImageDraw.ImageDraw, pos, text: str, font: ImageFont.ImageFont) -> None:
    try:
        draw.text(pos, text, font=font, fill=TEXT, anchor="rm", direction="rtl", language="ar")
    except (TypeError, ValueError):
        draw.text(pos, text, font=font, fill=TEXT, anchor="rm")


def add_page_branding(image: Image.Image, page_name: str | None = None) -> Image.Image:
    name = (page_name or os.getenv("KHYRAT_PAGE_NAME", DEFAULT_PAGE_NAME)).strip() or DEFAULT_PAGE_NAME
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    max_width = int(base.width * MAX_WIDTH_RATIO)
    size = FONT_SIZE
    font = _load_font(size)
    width, height = _measure(draw, name, font)
    while width > max_width and size > MIN_FONT_SIZE:
        size -= 2
        font = _load_font(size)
        width, height = _measure(draw, name, font)
    badge_width = min(base.width - 2 * MARGIN, width + 2 * PADDING)
    badge_height = max(HEIGHT, height + 32)
    right, bottom = base.width - MARGIN, base.height - MARGIN
    left, top = right - badge_width, bottom - badge_height
    draw.rounded_rectangle((left, top, right, bottom), radius=RADIUS, fill=BACKGROUND)
    accent = 6
    draw.rounded_rectangle((left + 18, top + 20, left + 18 + accent, bottom - 20), radius=3, fill=(214, 174, 92, 255))
    _draw(draw, (right - PADDING, top + badge_height // 2), name, font)
    return Image.alpha_composite(base, overlay).convert("RGB")
