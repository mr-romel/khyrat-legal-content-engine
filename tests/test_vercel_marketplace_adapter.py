import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "api" / "index.py"


def load_adapter():
    spec = importlib.util.spec_from_file_location("vercel_marketplace_adapter", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_adapter_imports_without_starting_server():
    module = load_adapter()
    assert hasattr(module, "handler")
    assert callable(module.handler)


def test_vercel_config_exists():
    config = (ROOT / "vercel.json").read_text(encoding="utf-8")
    assert "@vercel/python" in config
    assert "api/index.py" in config
