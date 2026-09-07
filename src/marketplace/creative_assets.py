"""Deterministic branded creative assets for Marketplace service packages.

These assets are presentation/cover graphics only. They are not represented as
client work samples and this module never publishes to marketplace platforms.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from PIL import Image, ImageDraw, ImageFont

KHAMSAT_COVER_SIZE = (1700, 970)
PORTFOLIO_SIZE = (800, 460)


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\u0600-\u06ff]+", "-", str(value).strip(), flags=re.UNICODE)
    return value.strip("-").lower() or "service"


def find_logo(search_roots: list[Path] | None = None) -> Path | None:
    roots = search_roots or [Path("generated"), Path(".")]
    names = ("ask mahmoud logo.png", "ask_mahmoud_logo.png", "ask-mahmoud-logo.png")
    for root in roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return candidate
    return None


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _base(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, "#f4f0e8")
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.rounded_rectangle((50, 50, w - 50, h - 50), radius=36, outline="#252525", width=5)
    draw.line((w * 0.10, h * 0.78, w * 0.90, h * 0.78), fill="#252525", width=4)
    draw.rectangle((w * 0.12, h * 0.18, w * 0.44, h * 0.60), outline="#252525", width=5)
    draw.polygon([(w * 0.61, h * 0.25), (w * 0.82, h * 0.25), (w * 0.72, h * 0.58)], outline="#252525")
    return image


def build_service_assets(
    service: dict[str, Any],
    output_dir: str | Path,
    *,
    logo_path: str | Path | None = None,
) -> dict[str, str]:
    """Create a Khamsat cover and a branded portfolio/preview image."""
    title = str(service.get("title", "service")).strip() or "service"
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    slug = slugify(title)

    cover = _base(KHAMSAT_COVER_SIZE)
    cover.save(output / f"{slug}-khamsat-cover.png", optimize=True)

    portfolio = _base(PORTFOLIO_SIZE)
    draw = ImageDraw.Draw(portfolio)
    font = _load_font(28)
    draw.text((90, 90), "Khyrat Legal", font=font, fill="#252525")
    draw.text((90, 135), "Service preview", font=_load_font(20), fill="#555555")

    chosen_logo = Path(logo_path) if logo_path else find_logo()
    if chosen_logo and chosen_logo.is_file():
        try:
            logo = Image.open(chosen_logo).convert("RGBA")
            logo.thumbnail((180, 100), Image.Resampling.LANCZOS)
            portfolio.paste(logo, (portfolio.width - logo.width - 70, 70), logo)
        except (OSError, ValueError):
            pass
    portfolio.save(output / f"{slug}-portfolio-preview.png", optimize=True)

    return {
        "cover": str(output / f"{slug}-khamsat-cover.png"),
        "portfolio_preview": str(output / f"{slug}-portfolio-preview.png"),
        "cover_size": f"{KHAMSAT_COVER_SIZE[0]}x{KHAMSAT_COVER_SIZE[1]}",
        "portfolio_size": f"{PORTFOLIO_SIZE[0]}x{PORTFOLIO_SIZE[1]}",
        "usage_note": "Brand/presentation asset only; not a client work sample.",
    }
