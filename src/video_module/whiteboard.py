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
        (("إيصال أمانة", "ايصال امانة", "أمانة", "امانة", "شيك", "فلوس"), "فلوس"),
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


def _hand(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    sw = max(5, int(8 * scale))
    palm = [(x, y), (x + 55 * scale, y - 18 * scale), (x + 92 * scale, y + 20 * scale),
            (x + 78 * scale, y + 75 * scale), (x + 25 * scale, y + 92 * scale),
            (x - 8 * scale, y + 55 * scale), (x, y)]
    draw.line(palm, fill=INK, width=sw, joint="curve")
    for dx in (18, 39, 60):
        draw.line((x + dx * scale, y + 8 * scale, x + (dx + 5) * scale, y - 50 * scale), fill=INK, width=sw)
    draw.line((x + 20 * scale, y + 55 * scale, x + 75 * scale, y + 28 * scale), fill=INK, width=sw)
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
        draw.polygon([(cx-180*s, cy-40*s), (cx, cy-175*s), (cx+180*s, cy-40*s)], outline=INK)
        draw.line((cx, cy-115*s, cx, cy+145*s), fill=PENCIL, width=lw)
        draw.line((cx-115*s, cy+45*s, cx+115*s, cy+45*s), fill=PENCIL, width=lw)
    elif kind == "أسرة":
        for dx, head in ((-90, 45), (0, 60), (90, 45)):
            draw.ellipse((cx+(dx-head)*s, cy-145*s, cx+(dx+head)*s, cy-55*s), outline=INK, width=lw)
            draw.arc((cx+(dx-70)*s, cy-50*s, cx+(dx+70)*s, cy+120*s), 180, 360, fill=INK, width=lw)
    elif kind == "شركة":
        draw.rectangle((cx-160*s, cy-160*s, cx+160*s, cy+150*s), outline=INK, width=lw)
        for dx in (-85, 0, 85):
            draw.rectangle((cx+(dx-28)*s, cy-90*s, cx+(dx+28)*s, cy-25*s), outline=PENCIL, width=max(6, lw-4))
        draw.line((cx-110*s, cy+65*s, cx+110*s, cy+65*s), fill=PENCIL, width=lw)
    elif kind == "قرار":
        draw.rectangle((cx-160*s, cy-150*s, cx+160*s, cy+150*s), outline=INK, width=lw)
        for off, end in ((-55, 65), (15, 95), (85, 35)):
            draw.line((cx-100*s, cy+off*s, cx+end*s, cy+off*s), fill=PENCIL, width=lw)
        draw.line((cx+75*s, cy+55*s, cx+125*s, cy+105*s), fill=INK, width=lw)
        draw.line((cx+125*s, cy+105*s, cx+205*s, cy+10*s), fill=INK, width=lw)
    else:
        draw.rectangle((cx-150*s, cy-140*s, cx+150*s, cy+130*s), outline=INK, width=lw)
        draw.line((cx-110*s, cy-50*s, cx+105*s, cy-50*s), fill=PENCIL, width=lw)
        draw.line((cx-110*s, cy+25*s, cx+65*s, cy+25*s), fill=PENCIL, width=lw)


def _text(draw: ImageDraw.ImageDraw, text: str, y: int, size: int = 48, bold: bool = False) -> None:
    shaped = _shape_ar(text)
    bbox = draw.textbbox((0, 0), shaped, font=_font(size, bold))
    x = (W - (bbox[2] - bbox[0])) // 2
    draw.text((x + 2, y + 2), shaped, font=_font(size, bold), fill=(190, 190, 190))
    draw.text((x, y), shaped, font=_font(size, bold), fill=INK)


def _frame(topic: str, kind: str, scene_index: int, phase: int, note: str) -> Image.Image:
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)
    if phase >= 1:
        _text(draw, topic if scene_index == 1 else f"النقطة {scene_index}", 150, 58, True)
        draw.line((120, 270, 960, 270), fill=PENCIL, width=5)
    if phase >= 2:
        _icon(draw, kind, W // 2, 690, 1)
        _text(draw, note, 1050, 46, True)
    if phase >= 3:
        _text(draw, "خلينا نبص على المهم", 1180, 43)
        draw.line((150, 1280, 900, 1280), fill=PENCIL, width=7)
    if phase >= 4:
        line_end = 280 + ((scene_index * 130) % 520)
        draw.line((150, 1280, line_end, 1280), fill=INK, width=10)
        _hand(draw, 180 + scene_index * 125, 1390 - (scene_index % 2) * 90, 1.15)
        _text(draw, note, 1480, 43)
        draw.line((150, 1600, 930, 1600), fill=PENCIL, width=5)
        draw.line((150, 1600, 420 + scene_index * 65, 1600), fill=INK, width=9)
    return image


def write_whiteboard_scenes(directory: Path, topic: str = "", content: str = "", count: int = 5) -> list[Path]:
    """Create progressive whiteboard animation frames, not just static cards."""
    directory.mkdir(parents=True, exist_ok=True)
    kinds = _keywords(topic, content)
    while len(kinds) < min(count, 5):
        kinds.append(kinds[-1])
    short_topic = re.sub(r"\s+", " ", topic).strip()[:46] or "سؤال قانوني مهم"
    notes = [
        "المعلومة الأساسية",
        "خد بالك من النقطة دي",
        "ده حقك فين؟",
        "تعمل إيه عمليًا؟",
        "الخلاصة اللي تهمك",
    ]
    outputs: list[Path] = []
    for scene_index in range(1, min(count, 5) + 1):
        kind = kinds[scene_index - 1]
        note = notes[scene_index - 1]
        for phase in range(1, 5):
            image = _frame(short_topic, kind, scene_index, phase, note)
            path = directory / f"whiteboard_{len(outputs)+1:02d}.png"
            image.save(path, optimize=True)
            outputs.append(path)
    return outputs
