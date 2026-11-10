from pathlib import Path


def test_reel_pipeline_uses_remotion_as_the_only_video_compositor():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    renderer = (root / "src" / "remotion_renderer.py").read_text(encoding="utf-8")
    composition = (root / "remotion" / "src" / "Reel.tsx").read_text(encoding="utf-8")

    assert "render_reel_with_remotion(" in source
    assert "build_fast_fallback_reel(" not in source
    assert "burn_sentence_subtitles" not in source
    assert "REEL_STAGE renderer=REMOTION" in renderer
    root_component = (root / "remotion" / "src" / "Root.tsx").read_text(encoding="utf-8")
    assert "width={1080}" in root_component and "height={1920}" in root_component
    assert "subtitles.map" in composition
    assert "final_duration = _media_duration(video_path)" in source
    assert "Reel delivery blocked: final duration" in source


def test_reel_subtitle_renderer_uses_one_adaptive_box_and_wraps_text():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_subtitles.py").read_text(encoding="utf-8")
    assert "Render one adaptive caption box that contains the entire spoken sentence" in source
    assert "lines = _wrap(draw, sentence, font" in source
    assert "Never truncate its text" in source
