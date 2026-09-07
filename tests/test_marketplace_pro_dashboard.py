from __future__ import annotations

import ast
from pathlib import Path


def test_professional_dashboard_module_compiles():
    path = Path(__file__).parents[1] / "src" / "marketplace" / "pro_dashboard.py"
    ast.parse(path.read_text(encoding="utf-8"))


def test_professional_dashboard_contains_desktop_mobile_and_manual_safety():
    text = (Path(__file__).parents[1] / "src" / "marketplace" / "pro_dashboard.py").read_text(encoding="utf-8")
    assert "لوحة التحكم الاحترافية" in text
    assert "نسخة الموبايل" in text
    assert "فتح المشروع على مستقل" in text
    assert "navigator.clipboard.writeText" in text
    assert "لا يسجل دخولًا أو ينشر تلقائيًا" in text
