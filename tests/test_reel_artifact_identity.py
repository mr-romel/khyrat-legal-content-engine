from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_each_reel_run_uses_an_isolated_source_and_run_directory():
    source = (ROOT / 'src' / 'reel_pipeline.py').read_text(encoding='utf-8')
    assert 'OUTPUT_ROOT / ("row_" + str(row_number)) / safe_source_id / ("run_" + run_id)' in source
    assert 'REEL_SOURCE_ID_MISSING' in source


def test_telegram_review_buttons_are_bound_to_video_fingerprint():
    source = (ROOT / 'src' / 'reel_pipeline.py').read_text(encoding='utf-8')
    worker = (ROOT / 'workers' / 'telegram-control' / 'src' / 'index.js').read_text(encoding='utf-8')
    assert '"Reel Video SHA256": video_sha256' in source
    assert 'reel_approve:id_' in source
    assert 'reel_reject:id_' in source
    assert 'REEL_TELEGRAM_CALLBACK_TOO_LONG' in source
    assert 'startsWith("id_")' in worker
    assert 'candidate["ID"]' in worker
    assert 'storedFingerprint.slice(0, 16) !== suppliedFingerprint' in worker
    assert 'زر المراجعة يخص نسخة فيديو قديمة أو غير مطابقة' in worker


def test_publisher_requires_exact_run_artifact_and_sha256():
    workflow = (ROOT / '.github' / 'workflows' / 'reel-publish-approved.yml').read_text(encoding='utf-8')
    assert "('run_'+run_id)" in workflow
    assert 'REEL_ARTIFACT_FINGERPRINT_MISMATCH' in workflow
    assert "rglob('daily-reel.mp4')" not in workflow
    assert "root=Path('review-package')/('row_'+str(artifact_row_number))/safe_source_id/('run_'+run_id)" in workflow
    assert "source_matches=" in workflow
    assert "latest_matches=" in workflow
    assert "int(plan.get('row_number',-1)) != artifact_row_number" in workflow
    assert 'REEL_ARTIFACT_PATH_MISMATCH' in workflow
    assert 'REEL_MANIFEST_IDENTITY_MISMATCH' in workflow
    assert 'REEL_MANIFEST_FINGERPRINT_MISMATCH' in workflow


def test_legacy_row_only_approval_recovery_is_removed():
    workflow = (ROOT / '.github' / 'workflows' / 'reel-publish-approved.yml').read_text(encoding='utf-8')
    assert 'recovery_run_id = "39073320925"' not in workflow
    assert 'Legacy row-only approval recovery intentionally removed' in workflow


def test_sheet_and_telegram_worker_include_reel_fingerprint_column():
    sheets = (ROOT / 'src' / 'sheets.py').read_text(encoding='utf-8')
    worker = (ROOT / 'workers' / 'telegram-control' / 'src' / 'index.js').read_text(encoding='utf-8')
    assert '"Reel Video SHA256"' in sheets
    assert '"Reel Video SHA256"' in worker
    assert 'A:BZ' in worker