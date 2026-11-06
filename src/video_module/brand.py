from __future__ import annotations

from pathlib import Path

from brand_identity import (
    BRAND_ACCENT, BRAND_DESCRIPTOR, BRAND_LOCKUP, BRAND_NAME,
    BRAND_PRIMARY, BRAND_SERVICE_AREA, BRAND_SLOGAN, PROFESSIONAL_TITLE,
    PROFESSIONAL_NAME,
)


def logo_path() -> Path | None:
    """Resolve the canonical supplied logo, with legacy path compatibility."""
    root = Path(__file__).resolve().parents[2]
    candidates = (
        root / "assets" / "branding" / "logo.png",
        root / "assets" / "branding" / "ask_mahmoud_3d.png",
        root / "لوجو اسال محمود 3دي.png",
    )
    return next((path for path in candidates if path.is_file()), None)


def brand_metadata() -> dict[str, str]:
    return {
        "brand": BRAND_NAME,
        "professional_name": PROFESSIONAL_NAME,
        "professional_title": PROFESSIONAL_TITLE,
        "lockup": BRAND_LOCKUP,
        "descriptor": BRAND_DESCRIPTOR,
        "service_area": BRAND_SERVICE_AREA,
        "slogan": BRAND_SLOGAN,
        "primary_color": "#0C1C30",
        "accent_color": "#BE974C",
    }
