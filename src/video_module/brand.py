from __future__ import annotations

from pathlib import Path


def logo_path() -> Path | None:
    root = Path(__file__).resolve().parents[2]
    for name in ("assets/branding/logo.png", "assets/branding/ask_mahmoud_3d.png"):
        path = root / name
        if path.is_file():
            return path
    return None
