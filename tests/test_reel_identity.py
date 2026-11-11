from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reel_source_lock_resolves_by_unique_immutable_id_before_row_number():
    source = (ROOT / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert "matches = [(index, candidate) for index, candidate in enumerate(rows)" in source
    assert "len(matches) != 1" in source
    assert "continuing by ID" in source
    assert "missing its immutable ID" in source
    assert "target_number = int(source_context.get(\"row_number\"))" not in source
    assert "locked ID=" in source


def test_telegram_reel_buttons_carry_immutable_id_and_fingerprint():
    pipeline = (ROOT / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    worker = (ROOT / "workers" / "telegram-control" / "src" / "index.js").read_text(encoding="utf-8")
    assert 'reel_approve:id_' in pipeline
    assert 'reel_reject:id_' in pipeline
    assert 'startsWith("id_")' in worker
    assert 'candidate["ID"]' in worker
    assert 'storedFingerprint.slice(0, 16) !== suppliedFingerprint' in worker
    assert 'REEL_TELEGRAM_CALLBACK_TOO_LONG' in pipeline


def test_manual_reel_and_bulk_recovery_workflows_do_not_depend_on_fixed_row_numbers():
    reel_now = (ROOT / ".github" / "workflows" / "reel-now.yml").read_text(encoding="utf-8")
    bulk = (ROOT / ".github" / "workflows" / "reel-bulk-recovery-queue.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in reel_now
    assert "inputs.source_id" in reel_now
    assert '"row_number": 147' not in reel_now
    assert "REEL_RECOVERY_SOURCE_IDS" in bulk
    assert "TARGET_ROWS" not in bulk
    assert "immutable source IDs" in bulk
    assert "Reel already has an external Facebook/YouTube video" in bulk
    assert '"Reel Facebook ID": ""' not in bulk
    assert '"Reel YouTube ID": ""' not in bulk
    assert "external_video_ids" in reel_now
