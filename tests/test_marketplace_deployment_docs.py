from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_marketplace_deployment_contract_is_documented():
    deployment = (ROOT / "docs" / "MARKETPLACE_DEPLOYMENT.md").read_text(encoding="utf-8")
    rollout = (ROOT / "docs" / "MARKETPLACE_ROLLOUT.md").read_text(encoding="utf-8")

    for text in (deployment, rollout):
        assert "Vercel" in text
        assert "Cloudflare D1" in text
        assert "Khamsat/Mostaql" in text or "Mostaql" in text
        assert "Marketplace" in text


def test_marketplace_deployment_files_exist():
    assert (ROOT / "api" / "index.py").exists()
    assert (ROOT / "src" / "marketplace" / "cloud_state.py").exists()
    assert (ROOT / "vercel.json").exists()
