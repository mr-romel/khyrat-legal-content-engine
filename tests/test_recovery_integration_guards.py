import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class RecoveryIntegrationGuardTests(unittest.TestCase):
    def test_refreshed_legal_evidence_reaches_mandatory_review(self):
        source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        self.assertIn('_prepare_editorial_assets(config=config, topic=topic, facebook_post=post, legal_sources=legal_sources)', source)
        self.assertIn('legal_sources=legal_sources,\n            angle=row.get("ملاحظات", ""),', source)

    def test_held_rows_are_excluded_before_stale_reclaim_and_selection(self):
        source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        self.assertIn('str(candidate_row.get("Recovery Next At", "") or "").strip().upper() != "HOLD" and is_stale_processing', source)
        self.assertIn('str(r.get("Recovery Next At", "") or "").strip().upper() != "HOLD" and _is_due', source)
        self.assertIn('str(r.get("Recovery Next At", "") or "").strip().upper() != "HOLD" and _failed_retry', source)

if __name__ == "__main__":
    unittest.main()
