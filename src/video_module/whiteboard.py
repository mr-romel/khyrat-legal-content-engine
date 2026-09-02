from __future__ import annotations

from pathlib import Path


SVG_TEMPLATE = '''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920">
<rect width="1080" height="1920" fill="white"/>
<g fill="none" stroke="#151515" stroke-width="10" stroke-linecap="round" stroke-linejoin="round">
{body}
</g>
<g fill="#151515" font-family="DejaVu Sans" font-size="42" text-anchor="middle">
<text x="540" y="1740">اسأل محمود</text>
</g>
</svg>'''

SCENES = [
    '''<circle cx="540" cy="760" r="190"/><path d="M540 570v380M430 950h220M390 650h300"/><path d="M390 650l-90 250h180zM690 650l-90 250h180z"/><path d="M300 900h180M600 900h180"/>''',
    '''<rect x="315" y="520" width="450" height="620" rx="18"/><path d="M390 680h300M390 790h260M390 900h210"/><path d="M650 1030l70 70 130-150"/>''',
    '''<path d="M350 610h380v500H350z"/><path d="M410 760h260M410 850h210M410 940h160"/><circle cx="540" cy="520" r="70"/><path d="M540 450v140"/>''',
    '''<circle cx="540" cy="820" r="250"/><path d="M540 680c-90 0-130 60-130 120 0 85 80 100 130 140 50-40 130-55 130-140 0-60-40-120-130-120z"/><path d="M540 570v-80M500 490h80"/>''',
    '''<path d="M300 980l150 150 330-390"/><circle cx="540" cy="830" r="330"/><path d="M350 1260h380"/>''',
]


def write_whiteboard_scenes(directory: Path, count: int = 5) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for index, body in enumerate(SCENES[:count], 1):
        path = directory / f"whiteboard_{index:02d}.svg"
        path.write_text(SVG_TEMPLATE.format(body=body), encoding="utf-8")
        outputs.append(path)
    return outputs
