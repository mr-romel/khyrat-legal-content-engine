from pathlib import Path


def test_both_whiteboard_overlay_paths_are_duration_bounded():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    cap = '"-t", f"{duration:.3f}", "-shortest", str(styled)]'
    assert source.count(cap) == 2, (
        "Both the main whiteboard overlay and emergency fallback must cap output "
        "to the source duration and stop when the shortest mapped stream ends."
    )
