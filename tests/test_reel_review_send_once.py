from pathlib import Path


def test_review_state_is_authoritative_even_when_runner_has_no_local_mp4():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert 'if reel_status in {"REVIEW", "APPROVED", "PUBLISHED"} and not force_regenerate:' in source
    assert "waiting for the user's decision and refusing another Telegram delivery" in source


def test_regeneration_requires_the_rejection_workflow_lock():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert 'if reel_status == "REGENERATING" and not force_regenerate:' in source
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "reel-regenerate-rejected.yml").read_text(encoding="utf-8")
    assert '"Reel Status": "REGENERATING"' in workflow
    assert 'REEL_FORCE_REGENERATE: "true"' in workflow
