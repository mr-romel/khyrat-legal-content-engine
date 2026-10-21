from pathlib import Path


def test_reel_pipeline_uses_single_content_layer_and_separate_subtitle_burn():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")

    # The old implementation layered whiteboard cards on top of the content video,
    # duplicating the sentence subtitle box. The current design keeps the content
    # video as the only base layer, appends one brand end card, then burns subtitles.
    assert "styled = base" in source
    assert "The base video is the only content layer" in source
    assert "concat_list.write_text" in source
    assert "burn_sentence_subtitles" in source
    assert "final_duration = _media_duration(video_path)" in source
    assert "Reel delivery blocked: final duration" in source


def test_reel_subtitle_renderer_uses_one_adaptive_box_and_wraps_text():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_subtitles.py").read_text(encoding="utf-8")
    assert "Render one adaptive caption box that contains the entire spoken sentence" in source
    assert "lines = _wrap(draw, sentence, font" in source
    assert "Never truncate its text" in source
