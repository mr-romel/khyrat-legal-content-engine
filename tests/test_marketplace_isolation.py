from __future__ import annotations

import subprocess
import sys


def test_marketplace_import_does_not_import_core_modules():
    code = "import sys; import marketplace; assert not any(name in sys.modules for name in ('main', 'config', 'sheets'))"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
