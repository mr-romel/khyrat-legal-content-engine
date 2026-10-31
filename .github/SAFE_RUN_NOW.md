# Safe immediate publishing run
Run the scheduled pipeline now without forcing republish. The explicit manual-safe path may publish exactly one earliest READY/FAILED/PARTIAL_FAILED row across the schedule; it must never republish a PUBLISHED row.
Trigger nonce: 2026-10-31T19:32:00Z
