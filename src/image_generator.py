from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont


def _find_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]

    for path in candidates:
        p = Path(path)
        if p.exists():
            return ImageFont.truetype(str(p), size=size)

    return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    words = re.findall(r"\S+", text or "")
    lines = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines[:6]


def create_legal_image(topic: str, image_brief: str, output_path: str) -> str:
    width, height = 1200, 1200
    image = Image.new("RGB", (width, height), "#F4F7FA")
    draw = ImageDraw.Draw(image)

    navy = "#13263A"
    gold = "#B7924A"
    gray = "#5C6670"
    white = "#FFFFFF"

    # Background blocks
    draw.rounded_rectangle(
        (55, 55, width - 55, height - 55),
        radius=36,
        fill=white,
        outline="#D7DDE3",
        width=3,
    )

    draw.rectangle((55, 55, width - 55, 230), fill=navy)

    # Decorative legal scale / pillars
    cx = width - 210
    draw.line((cx, 110, cx, 235), fill=gold, width=8)
    draw.line((cx - 100, 145, cx + 100, 145), fill=gold, width=8)

    draw.line((cx - 75, 150, cx - 115, 205), fill=gold, width=5)
    draw.line((cx - 75, 150, cx - 35, 205), fill=gold, width=5)
    draw.arc((cx - 140, 190, cx - 85, 220), 0, 180, fill=gold, width=5)
    draw.arc((cx - 65, 190, cx - 10, 220), 0, 180, fill=gold, width=5)

    title_font = _find_font(60, bold=True)
    body_font = _find_font(33, bold=False)
    small_font = _find_font(24, bold=False)

    title_lines = _wrap_text(draw, topic, title_font, width - 170)
    y = 300

    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        text_w = bbox[2] - bbox[0]
        draw.text(
            ((width - text_w) / 2, y),
            line,
            font=title_font,
            fill=navy,
        )
        y += 80

    # Short visual brief, intentionally subtle.
    brief = (image_brief or "").strip()
    if brief:
        brief_lines = _wrap_text(draw, brief, body_font, width - 180)
        y += 25
        for line in brief_lines[:4]:
            bbox = draw.textbbox((0, 0), line, font=body_font)
            text_w = bbox[2] - bbox[0]
            draw.text(
                ((width - text_w) / 2, y),
                line,
                font=body_font,
                fill=gray,
            )
            y += 52

    # Footer brand
    footer_y = height - 150
    draw.rounded_rectangle(
        (110, footer_y, width - 110, footer_y + 62),
        radius=18,
        fill=navy,
    )

    brand = "اسأل محمود  |  محمود خيرت - محامي"
    bbox = draw.textbbox((0, 0), brand, font=small_font)
    text_w = bbox[2] - bbox[0]
    draw.text(
        ((width - text_w) / 2, footer_y + 17),
        brand,
        font=small_font,
        fill=white,
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="JPEG", quality=92, optimize=True)

    return str(output)
