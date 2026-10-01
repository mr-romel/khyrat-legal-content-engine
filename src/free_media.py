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
                    "license": "cc0,pdm",
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
            if license_code not in {"cc0", "pdm", "publicdomain"}:
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
