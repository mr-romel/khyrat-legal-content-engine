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

    def test_http_code_collision_does_not_trigger_recovery_lane(self):
        for value in ("request id 4010", "trace 42977", "job-50219", "reference 5039"):
            self.assertEqual(classify_failure(value)[0], "UNKNOWN", value)
    def test_bounded_http_signatures_classify(self):
        self.assertEqual(classify_failure("HTTP 401 Unauthorized")[0], "AUTHORIZATION")
        self.assertEqual(classify_failure("HTTP 429 Too Many Requests")[0], "TRANSIENT_PROVIDER")
        self.assertEqual(classify_failure("upstream HTTP 503 Service Unavailable")[0], "TRANSIENT_PROVIDER")
    def test_structured_status_code_classifies(self):
        self.assertEqual(classify_failure("request failed", {"http_status": 401})[0], "AUTHORIZATION")
        self.assertEqual(classify_failure("request failed", {"status_code": 503})[0], "TRANSIENT_PROVIDER")
    def test_held_processing_and_ready_rows_are_not_due(self):
        now = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
        held_processing = {"الحالة": "PROCESSING", "وقت آخر تشغيل": (now-timedelta(hours=2)).isoformat(), "Recovery Next At": "HOLD"}
        held_ready = {"الحالة": "READY", "Recovery Next At": "HOLD"}
        self.assertTrue(is_stale_processing(held_processing, now))
        self.assertFalse(retry_is_due(held_processing, now))
        self.assertFalse(retry_is_due(held_ready, now))
    def test_retry_future_and_exact_due_boundary(self):
        now = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(retry_is_due({"Recovery Next At": (now+timedelta(seconds=1)).isoformat()}, now))
        self.assertTrue(retry_is_due({"Recovery Next At": now.isoformat()}, now))
    def test_stale_non_processing_row_is_not_stale(self):
        now = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
        old = (now-timedelta(hours=2)).isoformat()
        self.assertFalse(is_stale_processing({"الحالة":"READY","وقت آخر تشغيل":old},now))
    def test_fair_selector_normalizes_timezone_offsets(self):
        chosen = choose_fair_candidate([
            (2, {"وقت آخر تشغيل":"2026-11-21T10:00:00+02:00"}),
            (3, {"وقت آخر تشغيل":"2026-11-21T09:00:00+00:00"}),
        ])
        self.assertEqual(chosen[0], 2)

if __name__ == "__main__":
    unittest.main()
