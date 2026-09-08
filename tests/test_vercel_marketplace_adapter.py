import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "api" / "index.py"


def load_adapter():
    spec = importlib.util.spec_from_file_location("vercel_marketplace_adapter", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_adapter_imports_without_starting_server():
    module = load_adapter()
    assert hasattr(module, "handler")
    assert callable(module.handler)
    assert callable(module._load_state)
    assert callable(module._save_state)


def test_vercel_config_exists():
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert config["version"] == 2
    assert config["builds"][0]["use"] == "@vercel/python"
    assert config["builds"][0]["src"] == "api/index.py"
    assert config["routes"][0]["dest"] == "/api/index.py"


def test_cloud_state_module_is_optional():
    module = load_adapter()
    assert module.USE_D1 is False
    state = module._load_state()
    assert isinstance(state, dict)
    assert "opportunities" in state
