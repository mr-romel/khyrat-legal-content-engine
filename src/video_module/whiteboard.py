from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


W, H = 1080, 1920
INK = (28, 28, 28)
PENCIL = (90, 90, 90)
ACCENT = (45, 45, 45)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabicUI-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansArabicUI-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _shape_ar(text: str) -> str:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _keywords(topic: str, content: str) -> list[str]:
    text = f"{topic} {content}".lower()
    groups = [
        (("إيصال أمانة", "ايصال امانة", "أمانة", "امانة", "شيك"), "فلوس"),
        (("عقد", "عقود", "إيجار", "ايجار", "بيع", "شراء"), "عقد"),
        (("عمل", "عامل", "موظف", "فصل", "مرتب", "أجر", "اجازة"), "شغل"),
        (("ميراث", "ورث", "تركة", "ترِكة", "وصية"), "ميراث"),
        (("طلاق", "نفقة", "حضانة", "زواج", "أسرة", "اسرة"), "أسرة"),
        (("شركة", "شريك", "مساهم", "أسهم", "تأسيس"), "شركة"),
        (("قرار إداري", "قرار ادارى", "جهة إدارية", "جهة ادارية", "موظف حكومي"), "قرار"),
        (("محكمة", "دعوى", "حكم", "استئناف", "نقض"), "محكمة"),
    ]
    found = []
    for needles, label in groups:
        if any(n in text for n in needles):
            found.append(label)
    return found[:2] or ["قانون"]


def _hand(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0, angle: int = 0) -> None:
    # Simple black line-art hand holding a marker. It is deliberately drawn as
    # an illustration so the board has a visible "writer" rather than a static icon.
    sw = max(5, int(8 * scale))
    palm = [(x, y), (x + 55 * scale, y - 18 * scale), (x + 92 * scale, y + 20 * scale),
            (x + 78 * scale, y + 75 * scale), (x + 25 * scale, y + 92 * scale),
            (x - 8 * scale, y + 55 * scale), (x, y)]
    draw.line(palm, fill=INK, width=sw, joint="curve")
    for dx in (18, 39, 60):
        draw.line((x + dx * scale, y + 8 * scale, x + (dx + 5) * scale, y - 50 * scale), fill=INK, width=sw)
    draw.line((x + 20 * scale, y + 55 * scale, x + 75 * scale, y + 28 * scale), fill=INK, width=sw)
    # marker/pen held toward the writing area
    draw.line((x + 72 * scale, y - 38 * scale, x + 150 * scale, y - 115 * scale), fill=ACCENT, width=max(4, int(7 * scale)))
    draw.polygon([(x + 145 * scale, y - 120 * scale), (x + 160 * scale, y - 135 * scale), (x + 153 * scale, y - 105 * scale)], fill=ACCENT)


def _icon(draw: ImageDraw.ImageDraw, kind: str, cx: int, cy: int, s: int = 1) -> None:
    lw = 12 * s
    if kind == "فلوس":
        draw.ellipse((cx - 150*s, cy - 95*s, cx + 150*s, cy + 95*s), outline=INK, width=lw)
        draw.ellipse((cx - 35*s, cy - 45*s, cx + 35*s, cy + 45*s), outline=INK, width=lw)
        draw.line((cx - 70*s, cy, cx - 40*s, cy), fill=INK, width=lw)
        draw.line((cx + 40*s, cy, cx + 70*s, cy), fill=INK, width=lw)
    elif kind == "عقد":
        draw.rounded_rectangle((cx-150*s, cy-190*s, cx+150*s, cy+190*s), radius=25*s, outline=INK, width=lw)
        for off, ln in ((-70, 210), (0, 240), (70, 180)):
            draw.line((cx-105*s, cy+off*s, cx+(-105+ln)*s, cy+off*s), fill=PENCIL, width=max(6, lw-4))
        draw.line((cx+40*s, cy+95*s, cx+90*s, cy+145*s), fill=INK, width=lw)
        draw.line((cx+90*s, cy+145*s, cx+175*s, cy+45*s), fill=INK, width=lw)
    elif kind == "شغل":
        draw.rectangle((cx-155*s, cy-105*s, cx+155*s, cy+125*s), outline=INK, width=lw)
        draw.rectangle((cx-65*s, cy-150*s, cx+65*s, cy-100*s), outline=INK, width=lw)
        draw.line((cx-95*s, cy+10*s, cx+95*s, cy+10*s), fill=PENCIL, width=lw)
        draw.line((cx, cy-60*s, cx, cy+80*s), fill=INK, width=lw)
    elif kind == "ميراث":
        draw.rectangle((cx-150*s, cy-40*s, cx+150*s, cy+150*s), outline=INK, width=lw)
        draw.polygon([(cx-180*s, cy-40*s), (cx, cy-175*s), (cx+180*s, cy-40*s)], outline=INK, fill=None)
        draw.line((cx, cy-115*s, cx, cy+145*s), fill=PENCIL, width=lw)
        draw.line((cx-115*s, cy+45*s, cx+115*s, cy+45*s), fill=PENCIL, width=lw)
    elif kind == "أسرة":
        for dx, head in ((-90, 45), (0, 60), (90, 45)):
            draw.ellipse((cx+(dx-head)*s, cy-145*s, cx+(dx+head)*s, cy+(-55)*s), outline=INK, width=lw)
            draw.arc((cx+(dx-70)*s, cy-50*s, cx+(dx+70)*s, cy+120*s), 180, 360, fill=INK, width=lw)
    elif kind == "شركة":
        draw.rectangle((cx-160*s, cy-160*s, cx+160*s, cy+150*s), outline=INK, width=lw)
        for dx in (-85, 0, 85):
            draw.rectangle((cx+(dx-28)*s, cy-90*s, cx+(dx+28)*s, cy-25*s), outline=PENCIL, width=max(6, lw-4))
        draw.line((cx-110*s, cy+65*s, cx+110*s, cy+65*s), fill=PENCIL, width=lw)
    elif kind == "قرار":
        draw.rectangle((cx-160*s, cy-150*s, cx+160*s, cy+150*s), outline=INK, width=lw)
        draw.line((cx-100*s, cy-55*s, cx+65*s, cy-55*s), fill=PENCIL, width=lw)
        draw.line((cx-100*s, cy+15*s, cx+95*s, cy+15*s), fill=PENCIL, width=lw)
        draw.line((cx-100*s, cy+85*s, cx+35*s, cy+85*s), fill=PENCIL, width=lw)
        draw.line((cx+75*s, cy+55*s, cx+125*s, cy+105*s), fill=INK, width=lw)
        draw.line((cx+125*s, cy+105*s, cx+205*s, cy+10*s), fill=INK, width=lw)
    else:
        draw.line((cx-130*s, cy+110*s, cx-130*s, cy-70*s), fill=INK, width=lw)
        draw.line((cx-130*s, cy-70*s, cx+130*s, cy-70*s), fill=INK, width=lw)
        draw.line((cx+130*s, cy-70*s, cx+130*s, cy+110*s), fill=INK, width=lw)
        draw.line((cx-165*s, cy+110*s, cx+165*s, cy+110*s), fill=INK, width=lw)
        draw.line((cx-65*s, cy-70*s, cx, cy-145*s), fill=INK, width=lw)
        draw.line((cx, cy-145*s, cx+65*s, cy-70*s), fill=INK, width=lw)


def _draw_heading(draw: ImageDraw.ImageDraw, text: str, y: int) -> None:
    shaped = _shape_ar(text)
    bbox = draw.textbbox((0, 0), shaped, font=_font(58, True))
    x = (W - (bbox[2] - bbox[0])) // 2
    draw.text((x + 3, y + 3), shaped, font=_font(58, True), fill=(190, 190, 190))
    draw.text((x, y), shaped, font=_font(58, True), fill=INK)


def _draw_info(draw: ImageDraw.ImageDraw, lines: list[str], y: int) -> None:
    font = _font(43)
    for idx, line in enumerate(lines):
        shaped = _shape_ar(line)
        bbox = draw.textbbox((0, 0), shaped, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw.text((x, y + idx * 66), shaped, font=font, fill=INK)


def write_whiteboard_scenes(directory: Path, topic: str = "", content: str = "", count: int = 5) -> list[Path]:
    """Create topic-aware whiteboard cards with legal drawings, writing and a visible hand/marker."""
    directory.mkdir(parents=True, exist_ok=True)
    kinds = _keywords(topic, content)
    while len(kinds) < min(count, 5):
        kinds.append(kinds[-1])
    outputs: list[Path] = []
    short_topic = re.sub(r"\s+", " ", topic).strip()[:46] or "سؤال قانوني مهم"

    for index in range(1, min(count, 5) + 1):
        image = Image.new("RGB", (W, H), "white")
        draw = ImageDraw.Draw(image)
        kind = kinds[index - 1]
        _draw_heading(draw, short_topic if index == 1 else f"النقطة {index}", 180)
        _icon(draw, kind, W // 2, 760, 1)
        if index == 1:
            _draw_info(draw, [f"الموضوع: {kind}", "خلينا نفهمها ببساطة"], 1080)
        elif index == 2:
            _draw_info(draw, ["إيه اللي بيحصل؟", "ركز في النقطة دي"], 1060)
        elif index == 3:
            _draw_info(draw, ["إيه حقك؟", "وإيه اللي مينفعش يحصل؟"], 1060)
        elif index == 4:
            _draw_info(draw, ["الخلاصة العملية", "اعمل إيه دلوقتي؟"], 1060)
        else:
            _draw_info(draw, ["خلي المعلومة دي في بالك", "واسأل قبل ما تاخد خطوة"], 1060)
        # Each scene places the hand at a different writing position. The renderer
        # adds motion between scenes, so the hand visibly travels across the board.
        _hand(draw, 150 + index * 135, 1370 - (index % 2) * 80, scale=1.15)
        draw.line((170, 1485, 880, 1485), fill=PENCIL, width=6)
        draw.ellipse((W//2 - 7, 1710, W//2 + 7, 1724), fill=ACCENT)
        path = directory / f"whiteboard_{index:02d}.png"
        image.save(path, optimize=True)
        outputs.append(path)
    return outputs
