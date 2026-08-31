import os
import subprocess
import sys


def test_video_disabled_does_not_block_core_import():
    env = os.environ.copy()
    env["VIDEO_MODULE_ENABLED"] = "0"
    result = subprocess.run(
        [sys.executable, "-c", "import main; print('CORE_IMPORT_OK')"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "CORE_IMPORT_OK" in result.stdout
