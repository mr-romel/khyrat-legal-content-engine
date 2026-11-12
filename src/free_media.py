from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_MEDIA_RETRY = Retry(
    total=3,
    connect=3,
    read=2,
    status=3,
    backoff_factor=1.0,
    status_forcelist=(408, 425, 429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
    respect_retry_after_header=True,
)
_MEDIA_SESSION = requests.Session()
_MEDIA_SESSION.mount("https://", HTTPAdapter(max_retries=_MEDIA_RETRY))
_MEDIA_SESSION.mount("http://", HTTPAdapter(max_retries=_MEDIA_RETRY))

OPENVERSE_URL = "https://api.openverse.org/v1/images/"
UA = "Khyrat-Legal-Content-Engine/1.0 (legal-content-reel-generator)"


def fetch_openverse_images(terms: list[str], output_dir: Path, per_term: int = 3) -> list[Path]:
    """
    Fetch only public-domain / CC0 images from Openverse, without an API key.
    Each downloaded asset gets a local license/source record.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: list[Path] = []
    seen: set[str] = set()
    metadata: list[dict[str, Any]] = []

    for term in terms[:8]:
        try:
            response = _MEDIA_SESSION.get(
                OPENVERSE_URL,
                params={
                    "q": term,
                    "page_size": max(12, per_term * 5),
                    "license": "cc0,pdm,by",
                    "mature": "false",
                },
                headers={"User-Agent": UA, "Accept": "application/json"},
                timeout=30,
            )
            if not response.ok:
                continue
            results = response.json().get("results", [])
        except Exception:
            continue

        for item in results:
            url = str(item.get("url") or "").strip()
            if not url or url in seen:
                continue
            # Openverse aggregates openly licensed media; keep the strictest
            # no-attribution-required licenses for the automatic pipeline.
            license_code = str(item.get("license") or "").lower()
            if license_code not in {"cc0", "pdm", "publicdomain", "by"}:
                continue
            item_title = str(item.get("title") or "")
            item_description = str(item.get("description") or "")
            item_tags = " ".join(str(tag.get("name") or "") for tag in (item.get("tags") or []) if isinstance(tag, dict))
            if not _scene_metadata_matches_query(term, item_title, f"{item_description} {item_tags}"):
                continue
            seen.add(url)
            try:
                media = requests.get(
                    url,
                    headers={"User-Agent": UA},
                    timeout=45,
                    allow_redirects=True,
                )
                media.raise_for_status()
                content_type = media.headers.get("content-type", "").lower()
                if "image/" not in content_type:
                    continue
                ext = ".jpg"
                if "png" in content_type:
                    ext = ".png"
                elif "webp" in content_type:
                    ext = ".webp"
                path = output_dir / f"openverse_{len(assets)+1:02d}{ext}"
                path.write_bytes(media.content)
                if path.stat().st_size < 20_000:
                    path.unlink(missing_ok=True)
                    continue
                assets.append(path)
                metadata.append({
                    "file": str(path),
                    "query": term,
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "tags": [tag.get("name") for tag in (item.get("tags") or []) if isinstance(tag, dict)],
                    "creator": item.get("creator"),
                    "license": item.get("license"),
                    "license_version": item.get("license_version"),
                    "license_url": item.get("license_url"),
                    "source": item.get("source"),
                    "source_url": item.get("foreign_landing_url"),
                    "media_url": url,
                })
                if len([p for p in assets if p.exists()]) >= 12:
                    break
            except Exception:
                continue
        time.sleep(1.05)

    (output_dir / "sources.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return assets



WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"


_SCENE_STOPWORDS = {
    "about", "after", "along", "among", "around", "before", "beside", "between", "close",
    "contemporary", "modern", "professional", "editorial", "photorealistic", "realistic",
    "image", "scene", "photo", "photograph", "view", "showing", "with", "without",
    "from", "into", "over", "under", "near", "inside", "outside", "the", "and", "for",
    "that", "this", "their", "there", "while", "where", "which", "natural", "light",
    "clean", "bright", "warm", "soft", "subtle", "well", "lit", "egyptian", "setting",
    "على", "في", "من", "إلى", "الى", "عن", "مع", "بين", "هذا", "هذه", "ذلك", "تلك",
    "مشهد", "صورة", "لقطة", "حديث", "حديثة", "معاصر", "معاصرة", "احترافي", "احترافية",
    "واقعي", "واقعية", "واضح", "واضحة", "بدون", "دون", "داخل", "خارج", "أمام", "خلف",
}


def _meaningful_scene_tokens(value: str) -> set[str]:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).casefold()
    tokens = re.findall(r"[a-z][a-z-]{3,}|[\\u0600-\\u06ff]{3,}", text)
    return {token.strip("-") for token in tokens if token.strip("-") not in _SCENE_STOPWORDS}


def _scene_metadata_matches_query(query: str, title: str, description: str = "") -> bool:
    """Reject catalog results whose title/description do not describe the requested scene."""
    requested = _meaningful_scene_tokens(query)
    if not requested:
        return False
    observed = _meaningful_scene_tokens(f"{title} {description}")
    matches = requested & observed
    required = 1 if len(requested) == 1 else 2
    return len(matches) >= required


def fetch_wikimedia_images(terms: list[str], output_dir: Path, target: int = 8) -> list[Path]:
    """Keyless Wikimedia Commons fallback with license metadata recorded locally."""
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: list[Path] = []
    metadata: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term in terms[:8]:
        if len(assets) >= target:
            break
        try:
            r = requests.get(
                WIKIMEDIA_API,
                params={
                    "action": "query", "generator": "search", "gsrsearch": term,
                    "gsrnamespace": 6, "gsrlimit": 10, "prop": "imageinfo|info",
                    "iiprop": "url|mime|extmetadata", "iiurlwidth": 1280,
                    "format": "json", "formatversion": 2,
                },
                headers={"User-Agent": UA}, timeout=30,
            )
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", [])
        except Exception:
            continue
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            mime = str(info.get("mime") or "").lower()
            if not mime.startswith("image/"):
                continue
            meta = info.get("extmetadata") or {}
            license_name = str((meta.get("LicenseShortName") or {}).get("value") or "").strip()
            raw_description = str((meta.get("ImageDescription") or {}).get("value") or "")
            raw_object_name = str((meta.get("ObjectName") or {}).get("value") or "")
            scene_title = str(page.get("title") or "")
            if not _scene_metadata_matches_query(term, scene_title, f"{raw_object_name} {raw_description}"):
                print(f"Wikimedia scene result skipped: metadata does not match requested scene ({scene_title[:120]}).")
                continue
            allowed = {"CC0", "Public domain", "Public Domain", "CC BY", "CC BY-SA", "CC BY 4.0", "CC BY-SA 4.0"}
            if not any(x.lower() in license_name.lower() for x in allowed):
                continue
            url = str(info.get("thumburl") or info.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            try:
                media = requests.get(url, headers={"User-Agent": UA}, timeout=45)
                media.raise_for_status()
                ctype = media.headers.get("content-type", "").lower()
                if "image/" not in ctype:
                    continue
                ext = ".png" if "png" in ctype else ".webp" if "webp" in ctype else ".jpg"
                path = output_dir / f"wikimedia_{len(assets)+1:02d}{ext}"
                path.write_bytes(media.content)
                if path.stat().st_size < 20_000:
                    path.unlink(missing_ok=True)
                    continue
                assets.append(path)
                metadata.append({
                    "file": str(path), "query": term, "title": page.get("title"),
                    "description": raw_description,
                    "creator": (meta.get("Artist") or {}).get("value"),
                    "license": license_name,
                    "license_url": (meta.get("LicenseUrl") or {}).get("value"),
                    "source": "Wikimedia Commons",
                    "source_url": f"https://commons.wikimedia.org/wiki/{str(page.get('title','')).replace(' ', '_')}",
                    "media_url": url,
                })
                if len(assets) >= target:
                    break
            except Exception:
                continue
        time.sleep(0.5)
    if metadata:
        source_file = output_dir / "sources.json"
        existing = []
        if source_file.exists():
            try: existing = json.loads(source_file.read_text(encoding="utf-8"))
            except Exception: existing = []
        source_file.write_text(json.dumps(existing + metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return assets


def generate_legal_cards(output_dir: Path, topic: str, count: int = 6) -> list[Path]:
    """Generate original watermark-free legal visual cards locally as the final fallback."""
    from PIL import Image, ImageDraw, ImageFont
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    font_path = next((p for p in candidates if Path(p).exists()), None)
    font = ImageFont.truetype(font_path, 58) if font_path else ImageFont.load_default()
    small = ImageFont.truetype(font_path, 38) if font_path else ImageFont.load_default()
    labels = [
        "معلومة قانونية",
        "افهم موقفك القانوني",
        "راجع المستندات",
        "التفاصيل بتفرق",
        "خد قرارك على أساس صحيح",
        "اسأل محاميك قبل الخطوة الأخيرة",
    ]
    assets = []
    for i in range(count):
        path = output_dir / f"generated_card_{i+1:02d}.png"
        img = Image.new("RGB", (1080, 1920), (18, 24, 32))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((70, 170, 1010, 1750), radius=45, outline=(220, 220, 220), width=4)
        draw.ellipse((390, 360, 690, 660), outline=(220, 220, 220), width=8)
        draw.line((540, 660, 540, 1080), fill=(220, 220, 220), width=8)
        draw.line((380, 900, 700, 900), fill=(220, 220, 220), width=8)
        draw.text((540, 1220), labels[i % len(labels)], font=font, anchor="mm", fill=(245, 245, 245), align="center")
        draw.text((540, 1400), str(topic)[:55], font=small, anchor="mm", fill=(205, 205, 205), align="center")
        img.save(path, quality=92)
        assets.append(path)
    return assets


def cached_fallback_assets(root: Path, exclude_dir: Path, limit: int = 8) -> list[Path]:
    """Reuse previously cleared local assets when an external catalog is temporarily unavailable."""
    assets: list[Path] = []
    if not root.exists():
        return assets
    for path in sorted(root.glob("row_*/scenes/*")):
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"}:
            if path.parent.resolve() == exclude_dir.resolve():
                continue
            assets.append(path)
            if len(assets) >= limit:
                break
    return assets
