from __future__ import annotations

import os
import subprocess
import sys


def test_marketplace_import_does_not_import_core_modules():
    code = "import sys; import marketplace; assert not any(name in sys.modules for name in ('main', 'config', 'sheets'))"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((".", "src"))
    # -S prevents runner/site-level startup hooks from polluting the clean
    # interpreter used to verify Marketplace package isolation.
    result = subprocess.run(
        [sys.executable, "-S", "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
