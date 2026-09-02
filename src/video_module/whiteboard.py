from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def write_whiteboard_scenes(directory: Path, count: int = 5) -> list[Path]:
    """Create clean whiteboard-style legal illustration cards."""
    directory.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for index in range(1, min(count, 5) + 1):
        image = Image.new("RGB", (1080, 1920), "white")
        draw = ImageDraw.Draw(image)
        ink = (25, 25, 25)
        accent = (80, 80, 80)
        if index == 1:
            draw.line((540, 500, 540, 1120), fill=ink, width=12)
            draw.line((380, 620, 700, 620), fill=ink, width=12)
            draw.line((380, 620, 300, 930), fill=ink, width=10)
            draw.line((700, 620, 780, 930), fill=ink, width=10)
            draw.ellipse((220, 900, 380, 970), outline=ink, width=10)
            draw.ellipse((700, 900, 860, 970), outline=ink, width=10)
            draw.line((420, 1120, 660, 1120), fill=ink, width=14)
        elif index == 2:
            draw.rounded_rectangle((300, 500, 780, 1200), radius=25, outline=ink, width=12)
            for y, length in ((680, 300), (800, 340), (920, 250)):
                draw.line((390, y, 390 + length, y), fill=accent, width=10)
            draw.line((610, 1060, 690, 1140), fill=ink, width=16)
            draw.line((690, 1140, 820, 990), fill=ink, width=16)
        elif index == 3:
            draw.rectangle((300, 560, 720, 1180), outline=ink, width=12)
            draw.line((390, 740, 640, 740), fill=accent, width=10)
            draw.line((390, 850, 600, 850), fill=accent, width=10)
            draw.line((390, 960, 560, 960), fill=accent, width=10)
            draw.ellipse((610, 980, 820, 1190), outline=ink, width=12)
            draw.line((770, 1140, 890, 1260), fill=ink, width=18)
        elif index == 4:
            draw.ellipse((300, 540, 780, 1020), outline=ink, width=12)
            draw.arc((420, 650, 660, 900), 200, 70, fill=ink, width=18)
            draw.line((540, 900, 540, 950), fill=ink, width=18)
            draw.ellipse((525, 980, 555, 1010), fill=ink)
            draw.line((540, 420, 540, 520), fill=accent, width=10)
        else:
            draw.ellipse((280, 560, 800, 1080), outline=ink, width=12)
            draw.line((380, 820, 500, 940), fill=ink, width=20)
            draw.line((500, 940, 720, 700), fill=ink, width=20)
            draw.line((360, 1220, 720, 1220), fill=accent, width=10)
        draw.ellipse((520, 1510, 560, 1550), fill=accent)
        path = directory / f"whiteboard_{index:02d}.png"
        image.save(path, optimize=True)
        outputs.append(path)
    return outputs
