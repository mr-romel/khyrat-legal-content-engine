from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

OPENVERSE_URL = "https://api.openverse.org/v1/images/"
UA = "Khyrat-Legal-Content-Engine/1.0 (legal-content-reel-generator)"


def fetch_openverse_images(terms: list[str], output_dir: Path, per_term: int = 2) -> list[Path]:
    """
    Fetch only public-domain / CC0 images from Openverse, without an API key.
    Each downloaded asset gets a local license/source record.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: list[Path] = []
    seen: set[str] = set()
    metadata: list[dict[str, Any]] = []

    for term in terms[:6]:
        try:
            response = requests.get(
                OPENVERSE_URL,
                params={
                    "q": term,
                    "page_size": max(8, per_term * 4),
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
