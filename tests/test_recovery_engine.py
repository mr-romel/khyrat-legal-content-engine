import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from recovery_engine import classify_failure, next_retry_at, is_stale_processing, retry_is_due, choose_fair_candidate

class RecoveryEngineTests(unittest.TestCase):
    def test_auth_failure_is_held(self):
        cls, strategy, _ = classify_failure("HTTP 401 token has expired")
        self.assertEqual(cls, "AUTHORIZATION")
        self.assertEqual(strategy, "HOLD_AND_ALERT")
        self.assertIsNone(next_retry_at(datetime.now(timezone.utc), cls, 1))
    def test_visual_failure_selects_rebuild_strategy(self):
        cls, strategy, _ = classify_failure("IMAGE_QA_BLOCKED: semantic QA rejected")
        self.assertEqual(cls, "VISUAL_ASSET")
        self.assertEqual(strategy, "REBUILD_BRIEF_AND_ROTATE_PROVIDER")
    def test_retry_backoff_is_bounded(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertLessEqual(next_retry_at(now, "TRANSIENT_PROVIDER", 99)-now, timedelta(minutes=90))
    def test_hold_is_not_due(self):
        self.assertFalse(retry_is_due({"Recovery Next At": "HOLD"}, datetime.now(timezone.utc)))
    def test_stale_processing_is_reclaimed(self):
        now = datetime.now(timezone.utc)
        old = (now-timedelta(minutes=40)).isoformat()
        self.assertTrue(is_stale_processing({"الحالة":"PROCESSING","وقت آخر تشغيل":old},now))
        self.assertFalse(is_stale_processing({"الحالة":"PROCESSING","وقت آخر تشغيل":now.isoformat()},now))
    def test_fair_selector_chooses_oldest_attempt(self):
        chosen=choose_fair_candidate([(2,{"وقت آخر تشغيل":"2026-11-21T10:00:00+02:00"}),(3,{"وقت آخر تشغيل":"2026-11-21T09:00:00+02:00"})])
        self.assertEqual(chosen[0],3)
if __name__ == "__main__":
    unittest.main()
