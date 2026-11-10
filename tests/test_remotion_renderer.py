from pathlib import Path

from remotion_renderer import render_reel_with_remotion


def test_remotion_renderer_is_the_only_active_reel_video_builder():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert "render_reel_with_remotion(" in source
    assert "build_fast_fallback_reel(" not in source
    assert "MPT_REPO" not in source
    assert "MoneyPrinterTurbo" not in source
    assert "animated_ffmpeg" not in source


def test_remotion_project_has_vertical_branded_composition():
    root = Path(__file__).resolve().parents[1] / "remotion"
    reel = (root / "src" / "Reel.tsx").read_text(encoding="utf-8")
    registration = (root / "src" / "Root.tsx").read_text(encoding="utf-8")
    assert "width={1080}" in registration
    assert "height={1920}" in registration
    assert "KhyratLegalReel" in registration
    assert "interpolate(" in reel
    assert "spring(" in reel
    assert "Audio" in reel
    assert "subtitles.map" in reel


def test_renderer_rejects_incomplete_image_packs():
    import pytest
    with pytest.raises(RuntimeError, match="REMOTION_INPUT_INVALID"):
        render_reel_with_remotion(
            scenes=[],
            voice_audio=Path("missing-voice.wav"),
            slogan_audio=Path("missing-slogan.wav"),
            logo=Path("missing-logo.png"),
            script="نص تجريبي",
            output_video=Path("out.mp4"),
        )
